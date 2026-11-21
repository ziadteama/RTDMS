from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from dms_fusion import AlertPattern, FusionDecision

from rtdms_pi.payloads import (
    alert_payload,
    health_payload,
    physio_payload,
    status_payload,
    to_json_bytes,
)
from rtdms_pi.state import FaceReport, PhoneReport, PhysioReport, Snapshot

CONTRACT = Path(__file__).resolve().parents[2] / "contracts/pi-link"


def validate(name: str, payload: dict[str, object]) -> None:
    schema = json.loads((CONTRACT / "schemas" / f"{name}.schema.json").read_text())
    jsonschema.validate(payload, schema)
    if name in ("alert", "status", "physio"):
        assert len(to_json_bytes(payload)) <= 240


@pytest.mark.parametrize(
    "fixture", sorted((CONTRACT / "fixtures").glob("*.json")), ids=lambda p: p.stem
)
def test_real_fixtures(fixture: Path) -> None:
    validate(fixture.stem, json.loads(fixture.read_text()))


@pytest.mark.parametrize("pattern", list(AlertPattern))
def test_alert(pattern: AlertPattern) -> None:
    d = alert_payload(FusionDecision(pattern, ["眼" * 100] * 10), 1732117202.4)
    validate("alert", d)
    assert d["pattern"] == pattern.value
    assert " " not in to_json_bytes(d).decode()


def test_payloads_full_and_empty() -> None:
    s = Snapshot(
        face=FaceReport(
            "drowsy",
            perclos=0.31,
            openness=0.31,
            blink_rate=9.5,
            closure_ms=2400,
            face=True,
            calibrated=True,
            calibration="ok",
        ),
        phone=PhoneReport(False, True, 0.91),
        camera_ok=True,
        fps=14.3,
        temp_c=64.2,
        physio=PhysioReport(json.loads((CONTRACT / "fixtures/physio.json").read_text()), 100),
        t=100,
    )
    for snapshot in (s, Snapshot(t=100)):
        validate("status", status_payload(snapshot))
        validate("physio", physio_payload(snapshot))
    assert physio_payload(Snapshot(t=100)) == {"watch_connected": False, "t": 100}
    assert "calibration" not in status_payload(Snapshot())
    validate(
        "health",
        health_payload(
            cpu_pct=1.2,
            fps=14.3,
            uptime_s=5,
            camera=True,
            models={"fusion": "running"},
            temp_c=64.2,
            mem_used_mb=100,
            mem_total_mb=8000,
            disk_free_mb=9000,
        ),
    )


def test_worst_case_numeric_payloads() -> None:
    big = 1.2345678901234567e200
    s = Snapshot(
        face=FaceReport(
            "warning",
            perclos=big,
            openness=big,
            blink_rate=big,
            closure_ms=big,
            face=True,
            calibrated=True,
            calibration="calibrating",
        ),
        camera_ok=True,
        phone=PhoneReport(True, True, big),
        temp_c=big,
        physio=PhysioReport(
            {
                "watch_connected": True,
                "t": big,
                "hr_bpm": big,
                "rr_ms": [big] * 20,
                "fatigue_probability": big,
                "hrv_state": "degraded",
                "rmssd_ms": big,
                "quality": "degraded",
            },
            100,
        ),
    )
    validate("status", status_payload(s))
    validate("physio", physio_payload(s))
    assert "temp_c" not in status_payload(s)
    assert "quality" not in physio_payload(s)


def test_invalid_values_omitted() -> None:
    s = Snapshot(
        face=FaceReport("unknown", perclos=float("nan"), calibration="unknown"),
        physio=PhysioReport({"t": 1, "hrv_state": "unknown", "quality": "unknown"}, 1),
    )
    validate("status", status_payload(s))
    validate("physio", physio_payload(s))


def test_status_payload_no_face_or_camera_lost() -> None:
    s1 = Snapshot(
        face=FaceReport(
            "drowsy",
            perclos=0.4,
            openness=0.2,
            blink_rate=12.0,
            closure_ms=500.0,
            face=False,
        ),
        camera_ok=True,
    )
    p1 = status_payload(s1)
    validate("status", p1)
    assert p1["state"] == "unavailable"
    assert p1["face"] is False
    for k in ("perclos", "openness", "blink_rate", "closure_ms"):
        assert k not in p1

    s2 = Snapshot(
        face=FaceReport(
            "drowsy",
            perclos=0.4,
            openness=0.2,
            blink_rate=12.0,
            closure_ms=500.0,
            face=True,
        ),
        camera_ok=False,
    )
    p2 = status_payload(s2)
    validate("status", p2)
    assert p2["state"] == "unavailable"
    assert p2["face"] is False
    for k in ("perclos", "openness", "blink_rate", "closure_ms"):
        assert k not in p2
