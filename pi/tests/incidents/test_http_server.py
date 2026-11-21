from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from rtdms_pi.incidents.http_server import serve
from rtdms_pi.incidents.store import IncidentStore

TOKEN = "test-secret-token-http-server"


class MockReporter:
    def __init__(self) -> None:
        self.reported = False

    def report(
        self, req: dict[str, Any], clock_offset_ms: int | None = None, **kwargs: Any
    ) -> str:
        self.reported = True
        return "2024-11-20T15-40-02-400Z"


def test_incident_server_ephemeral_port(tmp_path: Path) -> None:
    store = IncidentStore(root=tmp_path)
    reporter = MockReporter()
    server = serve("127.0.0.1", 0, store, reporter, TOKEN)
    try:
        port = server.port
        assert port > 0
        base_url = f"http://127.0.0.1:{port}"

        # Unauthorized request
        req = urllib.request.Request(f"{base_url}/incidents")
        try:
            urllib.request.urlopen(req)
            raise AssertionError("expected 401")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401

        # Authorized GET /incidents
        req = urllib.request.Request(
            f"{base_url}/incidents", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data == []

        # Authorized POST /incident
        post_data = json.dumps({"t_crash": 1732117202400, "g_peak": 5.0}).encode()
        req = urllib.request.Request(
            f"{base_url}/incident",
            data=post_data,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["ok"] is True
            assert data["id"] == "2024-11-20T15-40-02-400Z"

        # Range request on clip.mp4
        inc_id = "2024-11-20T15-40-02-400Z"
        mp4_path = tmp_path / inc_id / "clip.mp4"
        mp4_path.parent.mkdir(parents=True, exist_ok=True)
        mp4_path.write_bytes(b"M" * 500)
        req = urllib.request.Request(
            f"{base_url}/incidents/{inc_id}/clip.mp4",
            headers={"Authorization": f"Bearer {TOKEN}", "Range": "bytes=100-199"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 206
            assert resp.headers.get("Content-Range") == "bytes 100-199/500"
            content = resp.read()
            assert content == b"M" * 100
    finally:
        server.stop()
