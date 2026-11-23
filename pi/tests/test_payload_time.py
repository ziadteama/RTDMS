import json
from urllib.request import urlopen

import pytest
from dms_fusion import AlertPattern, FusionDecision

from rtdms_pi.ble.uuids import Char
from rtdms_pi.clock import PhoneClock
from rtdms_pi.config import RuntimeConfig
from rtdms_pi.http_debug import DebugServer
from rtdms_pi.state import PhysioReport


@pytest.mark.parametrize("synced", [False, True])
def test_ble_http_times(service, clock, synced) -> None:
    from test_payloads import validate

    phone_clock = PhoneClock(monotonic=clock, wall=lambda: 1234)
    service.state.phone_clock = phone_clock
    if synced:
        phone_clock.on_clock_write(clock() * 1000, 1700000000000)
        phone_clock.on_clock_write(clock() * 1000 + 50, 1700000000000)
    service.state.update_physio(
        PhysioReport(
            {
                "watch_connected": True,
                "hr_bpm": 72,
                "worn": True,
                "quality": "good",
                "hr_baseline_bpm": 70,
                "hr_delta_bpm": 2,
                "hr_trend_bpm_per_10min": 0,
                "motion": 1,
                "wrist_still_s": 20,
                "ack_age_s": 2,
                "echo_seq": 7,
                "t": -999,
                "fatigue_probability": 0.9,
            },
            clock() - 1,
        )
    )
    expected = {
        "alert": (1700000000 if synced else 1234),
        "physio": (1699999999 if synced else 1234),
    }
    server = DebugServer(
        service.state,
        service.player,
        RuntimeConfig(host="127.0.0.1", http_port=0),
    )
    server.start()
    try:
        service.notifier.step()
        for char in (Char.ALERT, Char.PHYSIO):
            name = char.name.lower()
            with urlopen(f"http://127.0.0.1:{server.port}/{name}") as response:
                http = json.load(response)
            read = json.loads(service.port.read(char.uuid))
            notify = json.loads(
                next(raw for uuid, raw in service.port.notifications if uuid == char.uuid)
            )
            assert http == read == notify
            validate(name, http)
            assert http["t"] == expected[name]
            assert http["t_src"] == ("phone" if synced else "pi")
            assert (
                not {"motion", "wrist_still_s", "ack_age_s", "echo_seq", "fatigue_probability"}
                & http.keys()
            )
        service.state.set_decision(FusionDecision(AlertPattern.MAX, []))
        clock.advance(0.25)
        service.notifier.step()
        alerts = [
            json.loads(raw) for uuid, raw in service.port.notifications if uuid == Char.ALERT.uuid
        ]
        assert alerts[-1]["t"] == expected["alert"] + (0.25 if synced else 0)
    finally:
        server.stop()
