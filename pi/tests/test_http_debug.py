from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_payloads import validate

from rtdms_pi.buzzer import PatternPlayer, RecordingBuzzer
from rtdms_pi.config import RuntimeConfig
from rtdms_pi.http_debug import DebugServer
from rtdms_pi.state import RuntimeState


def test_http() -> None:
    player = PatternPlayer(RecordingBuzzer(), autostart=False)
    server = DebugServer(RuntimeState(), player, RuntimeConfig(host="127.0.0.1", http_port=0))
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    try:
        for name in ("alert", "status", "physio", "health"):
            with urlopen(base + "/" + name, timeout=2) as response:
                validate(name, json.load(response))
        req = Request(base + "/test_alert", data=b'{"pattern":"max"}', method="POST")
        with urlopen(req, timeout=2) as response:
            assert json.load(response) == {"ok": True}
        assert player._override is not None and player._override[0].value == "max"
        for body in (b"{}", b'{"pattern":"invalid"}', b"[]", b"not json"):
            with pytest.raises(HTTPError) as error:
                urlopen(Request(base + "/test_alert", data=body, method="POST"), timeout=2)
            assert error.value.code == 400
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/stream.mjpg", timeout=2)
        assert error.value.code == 404
    finally:
        server.stop()
        player.close()
    assert not server._thread.is_alive()
