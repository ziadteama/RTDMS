from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]

from rtdms_pi.incidents.http_routes import handle
from rtdms_pi.incidents.store import IncidentStore

CONTRACT = Path(__file__).resolve().parents[3] / "contracts/pi-link"
TOKEN = "test-secret-token-12345"


class MockReporter:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = fail

    def report(
        self, req: dict[str, Any], clock_offset_ms: int | None = None, **kwargs: Any
    ) -> str:
        if self.fail:
            raise RuntimeError("sink failure")
        self.calls.append(req)
        return "2024-11-20T15-40-02-400Z"


def test_auth_rejected(tmp_path: Path) -> None:
    store = IncidentStore(root=tmp_path)
    reporter = MockReporter()

    # Missing auth
    status, _, body = handle("GET", "/incidents", {}, b"", store, reporter, TOKEN)
    assert status == 401

    # Wrong token
    headers = {"Authorization": "Bearer wrong-token"}
    status, _, _ = handle("GET", "/incidents", headers, b"", store, reporter, TOKEN)
    assert status == 401


def test_get_incidents(tmp_path: Path) -> None:
    store = IncidentStore(root=tmp_path)
    meta = {
        "id": "2024-11-20T15-40-02-400Z",
        "t_crash": 1732117202400,
        "g_peak": 5.0,
        "duration_s": 25.0,
    }
    store.save_incident("2024-11-20T15-40-02-400Z", meta, [])

    headers = {"Authorization": f"Bearer {TOKEN}"}
    status, hdrs, body = handle("GET", "/incidents", headers, b"", store, MockReporter(), TOKEN)
    assert status == 200
    assert hdrs["Content-Type"] == "application/json"
    assert isinstance(body, bytes)
    items = json.loads(body)
    assert len(items) == 1
    assert items[0]["id"] == "2024-11-20T15-40-02-400Z"


def test_post_incident_validation(tmp_path: Path) -> None:
    req_schema = json.loads((CONTRACT / "schemas" / "incident_request.schema.json").read_text())
    resp_schema = json.loads((CONTRACT / "schemas" / "incident_response.schema.json").read_text())

    store = IncidentStore(root=tmp_path)
    reporter = MockReporter()
    headers = {"Authorization": f"Bearer {TOKEN}"}

    # Valid payload matching schema
    valid_body = {
        "t_crash": 1732117202400,
        "g_peak": 6.4,
        "lat": 31.2,
        "lon": 29.9,
        "client_id": "c-1234",
    }
    jsonschema.validate(valid_body, req_schema)
    status, _, body = handle(
        "POST", "/incident", headers, json.dumps(valid_body).encode(), store, reporter, TOKEN
    )
    assert status == 200
    assert isinstance(body, bytes)
    resp = json.loads(body)
    jsonschema.validate(resp, resp_schema)
    assert resp["ok"] is True
    assert resp["id"] == "2024-11-20T15-40-02-400Z"

    # Invalid payloads -> 400
    status, _, _ = handle(
        "POST", "/incident", headers, b'{"t_crash": 1732117202400}', store, reporter, TOKEN
    )
    assert status == 400

    bad_type_body = b'{"t_crash": "1732117202400", "g_peak": 2.0}'
    status, _, _ = handle("POST", "/incident", headers, bad_type_body, store, reporter, TOKEN)
    assert status == 400

    # Extra disallowed field is stripped per contract.validate
    extra_field_body = b'{"t_crash": 1732117202400, "g_peak": 2.0, "unknown": 123}'
    status, _, body = handle(
        "POST", "/incident", headers, extra_field_body, store, reporter, TOKEN
    )
    assert status == 200
    resp = json.loads(body)
    assert resp["ok"] is True


def test_post_incident_reporter_failure_returns_200(tmp_path: Path) -> None:
    resp_schema = json.loads((CONTRACT / "schemas" / "incident_response.schema.json").read_text())
    store = IncidentStore(root=tmp_path)
    failing_reporter = MockReporter(fail=True)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    valid_body = {"t_crash": 1732117202400, "g_peak": 6.4}

    status, _, body = handle(
        "POST",
        "/incident",
        headers,
        json.dumps(valid_body).encode(),
        store,
        failing_reporter,
        TOKEN,
    )
    assert status == 200
    assert isinstance(body, bytes)
    resp = json.loads(body)
    jsonschema.validate(resp, resp_schema)
    assert resp["ok"] is False


def test_get_incident_files(tmp_path: Path) -> None:
    store = IncidentStore(root=tmp_path)
    inc_id = "2024-11-20T15-40-02-400Z"
    meta = {"id": inc_id, "t_crash": 1732117202400, "g_peak": 5.0}
    store.save_incident(inc_id, meta, [])
    headers = {"Authorization": f"Bearer {TOKEN}"}

    # GET meta.json
    status, hdrs, _ = handle(
        "GET", f"/incidents/{inc_id}/meta.json", headers, b"", store, MockReporter(), TOKEN
    )
    assert status == 200
    assert hdrs["Content-Type"] == "application/json"

    # GET data.jsonl
    status, hdrs, _ = handle(
        "GET", f"/incidents/{inc_id}/data.jsonl", headers, b"", store, MockReporter(), TOKEN
    )
    assert status == 200
    assert hdrs["Content-Type"] == "application/x-ndjson"

    # GET clip.mp4 before it exists -> 404
    status, _, _ = handle(
        "GET", f"/incidents/{inc_id}/clip.mp4", headers, b"", store, MockReporter(), TOKEN
    )
    assert status == 404

    # Path traversal rejection -> 404
    status, _, _ = handle(
        "GET", "/incidents/../meta.json", headers, b"", store, MockReporter(), TOKEN
    )
    assert status == 404


def test_get_incident_clip_range(tmp_path: Path) -> None:
    store = IncidentStore(root=tmp_path)
    inc_id = "2024-11-20T15-40-02-400Z"
    meta = {"id": inc_id, "t_crash": 1732117202400, "g_peak": 5.0}
    store.save_incident(inc_id, meta, [])
    # 150 KB test file to test 64 KB chunking
    mp4_path = tmp_path / inc_id / "clip.mp4"
    mp4_path.write_bytes(b"B" * 150000)

    headers = {"Authorization": f"Bearer {TOKEN}"}

    # Full GET clip.mp4
    status, hdrs, _ = handle(
        "GET", f"/incidents/{inc_id}/clip.mp4", headers, b"", store, MockReporter(), TOKEN
    )
    assert status == 200
    assert hdrs["Content-Type"] == "video/mp4"
    assert hdrs["Content-Length"] == "150000"

    # Range request 206
    range_headers = dict(headers, Range="bytes=0-149999")
    status, hdrs, data = handle(
        "GET", f"/incidents/{inc_id}/clip.mp4", range_headers, b"", store, MockReporter(), TOKEN
    )
    assert status == 206
    assert hdrs["Content-Type"] == "video/mp4"
    assert hdrs["Content-Range"] == "bytes 0-149999/150000"
    assert hdrs["Content-Length"] == "150000"
    chunks = list(data)
    assert len(chunks) == 3  # 65536 + 65536 + 18928
    assert len(chunks[0]) == 65536
    assert len(chunks[1]) == 65536
    assert len(chunks[2]) == 18928
    assert b"".join(chunks) == b"B" * 150000
