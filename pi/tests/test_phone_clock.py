import logging
from unittest.mock import Mock

import pytest

from rtdms_pi.clock import PhoneClock
from rtdms_pi.config import RuntimeConfig


def test_minimum_and_last_ten() -> None:
    clock = PhoneClock(monotonic=lambda: 10, wall=lambda: 123)
    assert clock.offset_ms is None
    assert clock.payload_t(10) == (123, "pi")
    for offset in [5, 20, 10]:
        clock.on_clock_write(1000 + offset, 1000)
    assert clock.offset_ms == 5
    assert clock.payload_t(2) == (1.995, "phone")
    for _ in range(8):
        clock.on_clock_write(1030, 1000)
    assert clock.offset_ms == 10
    for _ in range(2):
        clock.on_clock_write(1040, 1000)
    assert clock.offset_ms == 30


@pytest.mark.parametrize("fail", [False, True])
def test_system_sync_once_per_process(monkeypatch, caplog, fail) -> None:
    monkeypatch.setattr("rtdms_pi.clock._sync_attempted", False)
    setter = Mock(side_effect=OSError("private") if fail else None)
    clock = PhoneClock(wall=lambda: 100, set_system_clock=setter)
    clock.on_clock_write(1000, 102000)  # exactly two seconds: no sync
    setter.assert_not_called()
    with caplog.at_level(logging.WARNING):
        clock.on_clock_write(2000, 103000)
        clock.on_clock_write(3000, 104000)
        PhoneClock(wall=lambda: 0, set_system_clock=setter).on_clock_write(0, 105000)
    setter.assert_called_once_with(103)
    assert len(caplog.records) == int(fail)
    assert "private" not in caplog.text
    assert clock.offset_ms == -101000


def test_config_sync_opt_in() -> None:
    assert not RuntimeConfig.from_args([]).sync_system_clock
    assert RuntimeConfig.from_args(["--sync-system-clock"]).sync_system_clock


def test_incidents_share_filtered_clock(service, clock) -> None:
    from test_ble_service import fixture, unlock, write

    from rtdms_pi.ble.uuids import Char
    from rtdms_pi.incidents_api import ClockedIncidentSink, MemoryIncidentSink

    unlock(service)
    write(service, Char.CLOCK, {"phone_ms": 1000})
    clock.advance(0.1)
    write(service, Char.CLOCK, {"phone_ms": 1000})  # delayed write must not replace minimum
    req = fixture("incident_request")
    write(service, Char.INCIDENT, req)
    ble = next(iter(service.incidents.items.values()))
    sink = MemoryIncidentSink()
    adapter = ClockedIncidentSink(sink, service.state.phone_clock)
    incident_id = adapter.report(req)
    assert sink.items[incident_id]["pi_crash_ms"] == ble["pi_crash_ms"]
    assert ble["pi_crash_ms"] == req["t_crash"] + 99000
