from __future__ import annotations

from conftest import Clock
from dms_fusion import AlertPattern, FusionDecision
from dms_physiology.garmin_rr import RrPacket, encode

from rtdms_pi.ble.phone_service import PhoneService
from rtdms_pi.ble.uuids import GARMIN_CHAR_UUID, Char
from rtdms_pi.watch_alert import WatchAlert


def watch_notifies(service: PhoneService) -> list[bytes]:
    return [data for uuid, data in service.port.notifications if uuid == Char.WATCH_ALERT.uuid]


def test_change_only_plus_keepalive(service: PhoneService, clock: Clock) -> None:
    service.notifier.step()
    assert watch_notifies(service) == [bytes((0, 0))]  # current state for a fresh watch
    service.state.set_decision(FusionDecision(AlertPattern.MAX, []))
    service.notifier.step()
    assert watch_notifies(service)[-1] == bytes((4, 1))
    clock.advance(1)
    service.notifier.step()
    assert len(watch_notifies(service)) == 2  # no change, keep-alive not yet due
    clock.advance(4)
    service.notifier.step()
    assert watch_notifies(service)[-1] == bytes((4, 1))  # 5 s keep-alive, same seq
    assert service.port.read(Char.WATCH_ALERT.uuid) == bytes((4, 1))


def test_seq_wraps() -> None:
    w = WatchAlert()
    for _ in range(256):
        value = w.change(AlertPattern.REPEATED)
    assert value == bytes((2, 0))


def test_echo_round_trip_is_timed_from_the_change(service: PhoneService, clock: Clock) -> None:
    service.state.set_decision(FusionDecision(AlertPattern.REPEATED, []))
    service.notifier.step()  # seq 1 sent (a change) at t=100
    clock.advance(0.04)
    packet = RrPacket(1, 1000, 70, (), version=2, contact=True, motion=0, echo_seq=1)
    service.port.write(GARMIN_CHAR_UUID, encode(packet))
    diag = service.watch_alert.diagnostics()
    assert diag["watch_alert_rtt_p50_ms"] == round(40.0, 3)
    service.port.write(GARMIN_CHAR_UUID, encode(RrPacket(2, 2000, 70, (), version=2,
                                                         echo_seq=1)))
    assert service.watch_alert.diagnostics() == diag  # one sample per seq


def test_late_watch_echo_is_not_latency(service: PhoneService, clock: Clock) -> None:
    service.notifier.step()  # seq 0 only ever goes out as a keep-alive: never timed
    service.state.set_decision(FusionDecision(AlertPattern.MAX, []))
    service.notifier.step()  # seq 1 change at t=100, but no watch is listening
    clock.advance(10)
    service.notifier.step()  # keep-alive delivers seq 1 to a watch that just connected
    for seq, echo in ((1, 1), (2, 0)):
        packet = RrPacket(seq, seq * 1000, 70, (), version=2, echo_seq=echo)
        service.port.write(GARMIN_CHAR_UUID, encode(packet))
    assert service.watch_alert.diagnostics()["watch_alert_rtt_p50_ms"] is None
