from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import Counter
from unittest.mock import patch

import pytest
from conftest import Clock
from dms_fusion import AlertPattern, FusionDecision
from dms_physiology.garmin_rr import RrPacket, encode

from rtdms_pi.ble.contract import validate
from rtdms_pi.ble.fake_gatt import FakeGatt
from rtdms_pi.ble.notifier import Notifier
from rtdms_pi.ble.phone_service import PhoneService
from rtdms_pi.ble.throttle import GarminLossMonitor
from rtdms_pi.ble.uuids import GARMIN_CHAR_UUID, Char
from rtdms_pi.payloads import to_json_bytes
from rtdms_pi.state import RuntimeState


@pytest.mark.parametrize("factor,counts", [(1, (11, 3, 3)), (0.5, (11, 2, 2))])
def test_rates(clock: Clock, factor: float, counts: tuple[int, ...]) -> None:
    port = FakeGatt(clock)
    state = RuntimeState(clock=clock)

    def emit(char, schema, payload):
        assert validate(schema, payload) is not None
        data = to_json_bytes(payload)
        assert len(data) <= 240
        port.notify(char.uuid, data)

    notifier = Notifier(state, clock, emit)
    notifier.set_throttle(factor)
    for i in range(1001):
        clock.t = 100 + i / 100
        notifier.step()
    actual = Counter(uuid for uuid, _ in port.notifications)
    assert tuple(actual[c.uuid] for c in (Char.ALERT, Char.STATUS, Char.PHYSIO)) == counts
    state.set_decision(FusionDecision(AlertPattern.MAX, ["眼" * 400] * 8))
    state.set_decision(FusionDecision(AlertPattern.REPEATED, []))
    notifier.step()
    assert [json.loads(data)["pattern"] for uuid, data in port.notifications[-2:]] == [
        "max",
        "repeated",
    ]
    notifier.close()


def test_loss_hysteresis() -> None:
    changes = []
    monitor = GarminLossMonitor(changes.append)
    for _ in range(60):
        monitor.record(False)
    for _ in range(3):
        monitor.record(True)
    assert monitor.factor == 1  # exactly 5%, not above
    monitor.record(True)
    assert changes == [0.5]
    for _ in range(58):
        monitor.record(False)
    assert monitor.factor == 0.5  # 2/60 is still above recovery threshold
    monitor.record(False)
    assert changes == [0.5, 1.0]


def test_garmin_before_pending_notifications(service: PhoneService) -> None:
    events = []
    receiver = service.garmin
    service.state.set_decision(FusionDecision(AlertPattern.MAX, []))
    with patch.object(receiver, "handle_write", wraps=receiver.handle_write) as handle:
        service.port.write(GARMIN_CHAR_UUID, encode(RrPacket(1, 1000, 72, (830,))))
        handle.assert_called_once()
        events.append("garmin")
        assert receiver.tracker.received == 1
        assert not service.port.notifications
        service.notifier.step()
        events.extend("notify" for _ in service.port.notifications)
    assert events == ["garmin", "notify", "notify", "notify"]
    service.port.write(GARMIN_CHAR_UUID, encode(RrPacket(8, 8000, 72, (830,))))
    assert service.notifier.factor == 0.5
    assert not service.auth.authed


@pytest.mark.asyncio
async def test_async_scheduler_stop(service: PhoneService) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(service.run(stop))
    await asyncio.sleep(0)
    stop.set()
    await asyncio.wait_for(task, 1)
    assert len(service.port.notifications) == 3


def test_change_during_drain_never_replays_old_snapshot(clock: Clock) -> None:
    state = RuntimeState(clock=clock)
    seen = []

    def emit(char, schema, payload):
        if char == Char.ALERT:
            seen.append(payload["pattern"])
            if payload["pattern"] == "max":
                state.set_decision(FusionDecision(AlertPattern.REPEATED, []))

    notifier = Notifier(state, clock, emit)
    state.set_decision(FusionDecision(AlertPattern.MAX, []))
    notifier.step()
    assert seen == ["max", "repeated"]
    notifier.close()


def _collector(clock: Clock):
    state = RuntimeState(clock=clock)
    seen: list[tuple[Char, dict]] = []
    notifier = Notifier(state, clock, lambda c, s, p: seen.append((c, p)))
    notifier.step()
    seen.clear()
    return state, notifier, seen


def _frame(state: RuntimeState, fps: float, temp_c: float, t: float) -> None:
    state.update_frame(None, None, fps, temp_c, False, t)


def test_status_deadband(clock: Clock) -> None:
    state, notifier, seen = _collector(clock)
    _frame(state, 30.0, 40.0, clock.t)
    clock.advance(1)
    notifier.step()
    assert [c for c, _ in seen if c == Char.STATUS] == [Char.STATUS]
    seen.clear()
    _frame(state, 30.2, 40.03, clock.t)
    clock.advance(1)
    notifier.step()
    assert not [c for c, _ in seen if c == Char.STATUS]
    _frame(state, 45.0, 40.03, clock.t)
    clock.advance(1)
    notifier.step()
    assert [c for c, _ in seen if c == Char.STATUS] == [Char.STATUS]
    notifier.close()


def test_decision_change_alerts_without_clock_advance(clock: Clock) -> None:
    state, notifier, seen = _collector(clock)
    state.set_decision(FusionDecision(AlertPattern.MAX, []))
    notifier.step()
    assert [p["pattern"] for c, p in seen if c == Char.ALERT] == ["max"]
    notifier.close()


@pytest.mark.asyncio
async def test_run_is_event_driven() -> None:
    state = RuntimeState()
    notifier = Notifier(state, time.time, lambda *_: None)
    stop = asyncio.Event()
    task = asyncio.create_task(notifier.run(stop))
    await asyncio.sleep(3.2)
    stop.set()
    await asyncio.wait_for(task, 1)
    assert notifier.wakeups <= 5
    notifier.close()


@pytest.mark.asyncio
async def test_thread_change_wakes_run() -> None:
    state = RuntimeState()
    seen: list[tuple[str, float]] = []
    notifier = Notifier(
        state,
        time.time,
        lambda c, s, p: seen.append((str(p.get("pattern", "")), time.monotonic())),
    )
    stop = asyncio.Event()
    task = asyncio.create_task(notifier.run(stop))
    await asyncio.sleep(0.1)
    sent = 0.0

    def fire() -> None:
        nonlocal sent
        sent = time.monotonic()
        state.set_decision(FusionDecision(AlertPattern.MAX, []))

    threading.Thread(target=fire).start()
    await asyncio.sleep(0.2)
    stop.set()
    await asyncio.wait_for(task, 1)
    got = [t for pat, t in seen if pat == "max"]
    assert got and got[0] - sent < 0.05
    notifier.close()


def test_no_validation_in_hot_path(service: PhoneService) -> None:
    with patch("rtdms_pi.ble.phone_service.validate") as v:
        service.notifier.step()
    v.assert_not_called()
    assert len(service.port.notifications) == 3


def test_validate_outgoing_rejects_invalid(service: PhoneService) -> None:
    service._emit(Char.ALERT, "alert", {"pattern": "bogus"})
    service.validate_outgoing = True
    with pytest.raises(ValueError):
        service._emit(Char.ALERT, "alert", {"pattern": "bogus"})
