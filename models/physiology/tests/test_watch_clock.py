"""Clock placement uses acquisition times even when BLE delivers a buffered burst."""

from dataclasses import replace

import pytest

from dms_physiology.garmin_hrv import RrHrv
from dms_physiology.garmin_rr import Arrival, RrPacket, SequenceTracker
from dms_physiology.watch_clock import WatchClock


def test_sixty_packet_replay() -> None:
    tracker, clock = SequenceTracker(), WatchClock()
    for seq in range(10):
        f = tracker.accept(RrPacket(seq, seq * 1000, 70, (850,)), 100 + seq + 0.02, 0)
        assert clock.add(f) == pytest.approx(100 + seq + 0.02)
    for seq in range(10, 70):
        f = tracker.accept(RrPacket(seq, seq * 1000, 70, (850,)), 169.04, 0)
        assert abs(clock.add(f) - (100 + seq)) < 0.05
    assert clock.late_packets == 58
    assert clock.offset_spread_ms == pytest.approx(59020)


def test_wrap_and_new_session() -> None:
    tracker, clock = SequenceTracker(), WatchClock()
    first = tracker.accept(RrPacket(65535, 2**32 - 500, 70, ()), 100, 0)
    assert clock.add(first) == 100
    wrapped = tracker.accept(RrPacket(0, 500, 70, ()), 103, 0)
    assert wrapped.arrival == Arrival.NEW
    assert clock.add(wrapped) == 101
    delayed = tracker.accept(RrPacket(1, 1500, 70, ()), 110, 0)
    assert clock.add(delayed) == 102
    assert clock.late_packets == 1
    restarted = tracker.accept(RrPacket(0, 2000, 70, ()), 111, 0)
    assert restarted.arrival == Arrival.NEW_SESSION
    assert clock.add(restarted) == 111
    assert clock.offset_spread_ms == 0
    assert clock.late_packets == 0


def test_sliding_min_max_expire_by_arrival_time() -> None:
    tracker, clock = SequenceTracker(), WatchClock(window_s=3)
    for seq, rx in enumerate([100.0, 102.0, 102.5, 104.5]):
        f = tracker.accept(RrPacket(seq, seq * 1000, 70, ()), rx, 0)
        assert clock.add(f) <= rx
    assert clock.offset_ms == 100500
    assert clock.offset_spread_ms == 1000


def test_hrv_accepts_placed_frame_without_mutating_arrival() -> None:
    tracker, clock, hrv = SequenceTracker(), WatchClock(), RrHrv()
    f = tracker.accept(RrPacket(1, 1000, 70, (850,)), 100, 0)
    clock.add(f)
    f = tracker.accept(RrPacket(2, 2000, 70, (850,)), 160, 0)
    t = clock.add(f)
    hrv.add(replace(f, rx_monotonic=t))
    assert hrv._beats[-1].t == 101
    assert f.rx_monotonic == 160


def test_reject_dropped_frames_and_invalid_window() -> None:
    with pytest.raises(ValueError):
        WatchClock(0)
    tracker, clock = SequenceTracker(), WatchClock()
    f = tracker.accept(RrPacket(1, 1000, 70, ()), 1, 0)
    clock.add(f)
    with pytest.raises(ValueError):
        clock.add(replace(f, arrival=Arrival.DUPLICATE))
    with pytest.raises(ValueError):
        clock.add(replace(f, arrival=Arrival.LATE))
