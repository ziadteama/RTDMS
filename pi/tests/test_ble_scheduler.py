from __future__ import annotations

import asyncio
import json
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


@pytest.mark.parametrize("factor,counts", [(1, (51, 21, 11)), (0.5, (51, 11, 6))])
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
    receiver = service.garmin.receiver
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
