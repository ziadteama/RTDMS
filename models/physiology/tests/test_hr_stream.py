"""Quality gates and session context on deterministic one-second HR batches."""

from dataclasses import replace

import pytest

from dms_physiology.garmin_rr import Arrival, RrFrame, RrPacket
from dms_physiology.hr_stream import HrStream


def frame(t: float, bpm: int | None = 70, contact: bool | None = True,
          motion: int | None = 0) -> RrFrame:
    p = RrPacket(int(t) % 65536, int(t * 1000) % 2**32, bpm, (),
                 version=2, contact=contact, motion=motion)
    return RrFrame(p, t, 0, Arrival.NEW, 0, False, 1)


def feed(stream: HrStream, start: int, stop: int, bpm: int | None = 70) -> None:
    for t in range(start, stop):
        stream.add(frame(t, bpm), float(t))


@pytest.mark.parametrize(('bpm', 'contact', 'motion', 'now', 'quality'), [
    (70, True, 0, 30, 'good'),
    (70, True, 159, 35, 'good'),
    (70, True, 0, 35.01, 'bad'),
    (70, False, 0, 30, 'bad'),
    (70, True, 160, 30, 'bad'),
    (96, True, 0, 30, 'bad'),
    (95, True, 0, 30, 'good'),
    (44, True, 0, 30, 'bad'),
    (45, True, 0, 30, 'good'),
    (70, None, None, 30, 'good'),
])
def test_quality_table(bpm: int, contact: bool | None, motion: int | None,
                       now: float, quality: str) -> None:
    stream = HrStream()
    feed(stream, 0, 30)
    stream.add(frame(30, bpm, contact, motion), 30)
    snap = stream.snapshot(now)
    assert snap.quality == quality
    assert snap.worn == contact
    assert snap.age_s == pytest.approx(now - 30)


def test_coverage_missing_packets_and_invalid_hr() -> None:
    stream = HrStream()
    feed(stream, 0, 23)
    assert stream.snapshot(22).quality == 'degraded'
    feed(stream, 23, 24)
    assert stream.snapshot(23).quality == 'good'
    feed(stream, 24, 31, None)
    snap = stream.snapshot(30)
    assert snap.quality == 'degraded'
    assert snap.hr_bpm == 70
    stream = HrStream()
    for t in range(0, 60, 2):
        stream.add(frame(t), t)
    assert stream.snapshot(58).quality == 'degraded'


def test_baseline_delta_and_linear_trend() -> None:
    stream = HrStream()
    for t in range(300):
        # Exactly linear, integer bpm data; regression excludes degraded startup samples.
        stream.add(frame(t, 50 + t // 10), t)
        if t == 141:
            assert stream.snapshot(t).hr_baseline_bpm is None
            assert stream.snapshot(t).hr_trend_bpm_per_10min is None
        if t == 142:
            assert stream.snapshot(t).hr_baseline_bpm is not None
    snap = stream.snapshot(299)
    assert snap.hr_baseline_bpm == 66
    assert snap.hr_delta_bpm == 13
    assert snap.hr_trend_bpm_per_10min == pytest.approx(60, abs=0.1)
    feed(stream, 300, 1000, 90)
    snap = stream.snapshot(999)
    assert snap.hr_baseline_bpm == 66
    assert snap.hr_delta_bpm == 24
    assert snap.hr_trend_bpm_per_10min == pytest.approx(0)
    assert len(stream._samples) == 600
    assert stream.snapshot(1700).hr_trend_bpm_per_10min is None


def test_exact_linear_slope_at_large_uptime() -> None:
    stream = HrStream()
    for i in range(150):
        t = 1e9 + i
        stream.add(frame(t, 50 + i), t)
    assert stream.snapshot(t).hr_trend_bpm_per_10min == pytest.approx(600)


def test_bad_samples_never_enter_baseline_or_trend() -> None:
    stream = HrStream()
    for t in range(301):
        stream.add(frame(t, 90, motion=160), t)
    feed(stream, 301, 400)
    snap = stream.snapshot(399)
    assert snap.hr_baseline_bpm is None
    assert snap.hr_trend_bpm_per_10min is None


def test_reset_and_empty() -> None:
    stream = HrStream()
    assert stream.snapshot(0).quality == 'bad'
    assert stream.snapshot(0).age_s is None
    feed(stream, 0, 200)
    stream.add(replace(frame(200, None), arrival=Arrival.NEW_SESSION, session=2), 200)
    snap = stream.snapshot(200)
    assert snap.hr_bpm is None
    assert snap.hr_baseline_bpm is None
    assert snap.hr_trend_bpm_per_10min is None
    assert snap.quality == 'degraded'


def test_v1_unknown_sensors_and_split_packets() -> None:
    stream = HrStream()
    for t in range(30):
        f = replace(frame(t), packet=RrPacket(t, t * 1000, 70, ()))
        stream.add(f, t)
    assert stream.snapshot(29).quality == 'good'
    assert stream.snapshot(29).worn is None
    stream = HrStream()
    for _ in range(200):
        stream.add(frame(0), 0)
    assert stream.snapshot(0).quality == 'degraded'
    assert stream.snapshot(0).hr_baseline_bpm is None
    assert len(stream._samples) == 1


def test_snapshot_during_outage_does_not_destroy_replay_coverage() -> None:
    stream = HrStream()
    feed(stream, 0, 30)
    assert stream.snapshot(90).quality == 'bad'
    feed(stream, 30, 90)
    assert stream.snapshot(89).quality == 'good'


def test_dropped_frames_do_not_change_hr() -> None:
    stream = HrStream()
    feed(stream, 0, 30)
    for arrival in (Arrival.DUPLICATE, Arrival.LATE):
        stream.add(replace(frame(30, 200), arrival=arrival), 30)
    assert stream.snapshot(30).hr_bpm == 70
