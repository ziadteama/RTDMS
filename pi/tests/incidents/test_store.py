from __future__ import annotations

import json
from collections import namedtuple
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]

from rtdms_pi.incidents.ring import Entry
from rtdms_pi.incidents.store import IncidentStore

CONTRACT = Path(__file__).resolve().parents[3] / "contracts/pi-link"
DiskUsage = namedtuple("DiskUsage", ["total", "used", "free"])


def _sample_entries() -> list[Entry]:
    return [
        Entry(
            t_mono=1.0,
            t_wall=100.0,
            jpeg=b"\xff\xd8\xff\xd9",
            status={
                "fps": 10.0,
                "face": True,
                "state": "alert",
                "perclos": 0.15,
                "hr_bpm": 80,  # Biometric fields that MUST be dropped by allowlist
                "hr": 80,
                "rr": 800,
                "rmssd": 50,
                "fatigue": 0.9,
                "physio": {"raw": 123},
            },
            alert={
                "pattern": "warning",
                "reasons": ["drowsy"],
                "t": 100.0,
                "rr_ms": 800,
                "rmssd": 45,
            },
        )
    ]


def test_save_incident_and_no_biometrics(tmp_path: Path) -> None:
    store = IncidentStore(root=tmp_path)
    meta = {
        "id": "2024-11-20T15-40-02-400Z",
        "client_id": "test-client-1",
        "t_crash": 1732117202400,
        "g_peak": 4.5,
        "lat": 31.2,
        "lon": 29.9,
    }
    target_dir = store.save_incident("2024-11-20T15-40-02-400Z", meta, _sample_entries())
    assert target_dir.is_dir()
    assert (target_dir / "meta.json").is_file()
    assert (target_dir / "clip.avi").is_file()
    assert (target_dir / "data.jsonl").is_file()

    # Verify no biometric keys are in data.jsonl, but allowlisted keys are retained
    jsonl_content = (target_dir / "data.jsonl").read_text(encoding="utf-8")
    parsed_row = json.loads(jsonl_content.strip())
    assert parsed_row["status"]["fps"] == 10.0
    assert parsed_row["status"]["face"] is True
    assert parsed_row["status"]["perclos"] == 0.15
    assert parsed_row["alert"]["pattern"] == "warning"
    for forbidden in ("hr_bpm", "hr", "rr", "rmssd", "fatigue", "physio", "rr_ms"):
        assert forbidden not in jsonl_content


def test_list_items_validates_schema(tmp_path: Path) -> None:
    schema = json.loads((CONTRACT / "schemas" / "incident_item.schema.json").read_text())
    store = IncidentStore(root=tmp_path)
    meta = {
        "id": "2024-11-20T15-40-02-400Z",
        "client_id": "c1",
        "t_crash": 1732117202400,
        "g_peak": 5.2,
        "lat": 31.2,
        "lon": 29.9,
        "duration_s": 25.0,
    }
    store.save_incident("2024-11-20T15-40-02-400Z", meta, [])

    items = store.list_items()
    assert len(items) == 1
    assert items[0]["clip_ready"] is False
    jsonschema.validate(items[0], schema)

    # Make clip.mp4 exist and verify clip_ready changes to True
    (tmp_path / "2024-11-20T15-40-02-400Z" / "clip.mp4").write_bytes(b"dummy-mp4")
    items2 = store.list_items()
    assert items2[0]["clip_ready"] is True
    jsonschema.validate(items2[0], schema)


def test_retention(tmp_path: Path) -> None:
    store = IncidentStore(root=tmp_path, max_incidents=3)
    for i in range(5):
        inc_id = f"2024-11-20T15-40-0{i}-000Z"
        meta = {
            "id": inc_id,
            "client_id": f"c_{i}",
            "t_crash": 1732117200000 + i * 1000,
            "g_peak": 3.0,
        }
        store.save_incident(inc_id, meta, [])

    dirs = [d.name for d in tmp_path.iterdir() if d.is_dir()]
    assert len(dirs) <= 3
    # Oldest 0 and 1 should have been purged
    assert "2024-11-20T15-40-00-000Z" not in dirs
    assert "2024-11-20T15-40-01-000Z" not in dirs
    assert "2024-11-20T15-40-04-000Z" in dirs


def test_disk_full_refusal_records_client_id(tmp_path: Path) -> None:
    # Free space 100 MB (< min_free_mb 500)
    def fake_usage(p: Path) -> DiskUsage:
        mb = 1024 * 1024
        return DiskUsage(total=1000 * mb, used=900 * mb, free=100 * mb)

    store = IncidentStore(root=tmp_path, min_free_mb=500, disk_usage=fake_usage)
    meta = {
        "id": "2024-11-20T15-40-02-400Z",
        "client_id": "c_full",
        "t_crash": 1732117202400,
        "g_peak": 4.0,
    }
    target = store.save_incident("2024-11-20T15-40-02-400Z", meta, _sample_entries())
    assert target.is_dir()
    assert (target / "meta.json").is_file()
    # Refused to write media
    assert not (target / "clip.avi").exists()
    assert not (target / "data.jsonl").exists()
    meta_saved = json.loads((target / "meta.json").read_text())
    assert "disk full" in meta_saved.get("error", "")
    assert meta_saved.get("frames") == 0
    # Must still index client_id for retry idempotency
    assert store.find_by_client_id("c_full") == "2024-11-20T15-40-02-400Z"


def test_save_incident_tolerant_of_none_jpegs(tmp_path: Path) -> None:
    store = IncidentStore(root=tmp_path)
    entries = [
        Entry(t_mono=1.0, t_wall=100.0, jpeg=None, status={"fps": 10.0}, alert={}),
        Entry(t_mono=1.1, t_wall=100.1, jpeg=None, status={"fps": 10.0}, alert={}),
    ]
    meta = {"id": "2024-11-20T15-40-02-400Z", "t_crash": 1732117202400, "g_peak": 3.0}
    target = store.save_incident("2024-11-20T15-40-02-400Z", meta, entries)
    assert (target / "clip.avi").is_file()
    saved_meta = json.loads((target / "meta.json").read_text())
    assert saved_meta["frames"] == 0


def test_path_traversal_rejection(tmp_path: Path) -> None:
    store = IncidentStore(root=tmp_path)
    meta = {"id": "2024-11-20T15-40-02-400Z", "t_crash": 1732117202400, "g_peak": 3.0}
    store.save_incident("2024-11-20T15-40-02-400Z", meta, [])

    # Valid file
    assert store.path("2024-11-20T15-40-02-400Z", "meta.json") is not None

    # clip.mp4 not ready -> returns None
    assert store.path("2024-11-20T15-40-02-400Z", "clip.mp4") is None

    # Traversal and invalid id attempts rejected by regex alone
    assert store.path("invalid-id", "meta.json") is None
    assert store.path("../", "meta.json") is None
    assert store.path("2024-11-20T15-40-02-400Z", "../meta.json") is None
    assert store.path("2024-11-20T15-40-02-400Z", "evil.txt") is None
