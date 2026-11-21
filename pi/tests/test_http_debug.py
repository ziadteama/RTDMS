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


def test_health_models_distraction_reporting() -> None:
    import time

    state = RuntimeState()
    # Camera ok, but phone report is None (driver turned away) -> distraction must report "running"
    state.update_frame(None, None, 15.0, None, True, time.monotonic())
    player = PatternPlayer(RecordingBuzzer(), autostart=False)
    cfg_camera = RuntimeConfig(host="127.0.0.1", http_port=0, no_camera=False)
    server = DebugServer(state, player, cfg_camera)
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    try:
        with urlopen(base + "/health", timeout=2) as resp:
            data = json.load(resp)
            assert data["models"]["distraction"] == "running"

        # When camera/pipeline is lost -> "error"
        state.update_frame(None, None, 0.0, None, False, time.monotonic())
        with urlopen(base + "/health", timeout=2) as resp:
            data = json.load(resp)
            assert data["models"]["distraction"] == "error"
    finally:
        server.stop()
        player.close()

    # When detector is disabled (no_camera=True) -> "off"
    cfg_nocam = RuntimeConfig(host="127.0.0.1", http_port=0, no_camera=True)
    server_nocam = DebugServer(state, player, cfg_nocam)
    server_nocam.start()
    base_nocam = f"http://127.0.0.1:{server_nocam.port}"
    try:
        with urlopen(base_nocam + "/health", timeout=2) as resp:
            data = json.load(resp)
            assert data["models"]["distraction"] == "off"
    finally:
        server_nocam.stop()

