"""Garmin RR -> HRV: filter, window, features and quality on synthetic beat streams."""

from __future__ import annotations

import math

import numpy as np
import pytest

from dms_physiology.garmin_hrv import HrvState, RrHrv
from dms_physiology.garmin_rr import RrPacket, SequenceTracker
from dms_physiology.types import QualityReason, QualityState


def feed(hrv: RrHrv, rr: list[float], *, drop_seqs: set[int] = frozenset(),
         restart_at: int | None = None, pause_after: int | None = None, pause_s: float = 0.0,
         t0: float = 100.0) -> float:
    """Pack beats one per packet, as the watch roughly does, and push them through the real
    SequenceTracker so loss / gaps / sessions behave exactly like the live path.
    Returns the Pi time of the last packet."""
    tracker = SequenceTracker()
    t, seq, watch_ms = t0, 0, 5_000_000
    for i, value in enumerate(rr):
        t += value / 1000.0
        watch_ms += int(value)
        if pause_after is not None and i == pause_after:
            t += pause_s
            watch_ms += int(pause_s * 1000)
        if restart_at is not None and i == restart_at:
            seq = 0
        packet = RrPacket(seq=seq % 65536, watch_ms=watch_ms, hr_bpm=70, rr_ms=(int(value),))
        seq += 1
        if packet.seq in drop_seqs and (restart_at is None or i < restart_at):
            continue  # lost over the air
        hrv.add(tracker.accept(packet, t, 1.8e9 + t))
    return t


def steady(n: int, mean: float = 850.0, swing: float = 40.0, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    k = np.arange(n)
    return list(np.round(mean + swing * np.sin(2 * np.pi * k / 5.0) + rng.normal(0, 8, n)))


def test_clean_stream_matches_hand_computation() -> None:
    rr = steady(120)
    hrv = RrHrv()
    t = feed(hrv, rr)
    snap = hrv.compute(t)
    assert snap.state == HrvState.VALID
    assert snap.quality.state == QualityState.GOOD
    assert snap.features is not None
    # beats whose end time is inside the last 60 s, computed by hand
    ends = 100.0 + np.cumsum(np.asarray(rr) / 1000.0)
    win = np.asarray(rr)[ends > t - 60.0]
    d = np.diff(win)
    assert snap.features.rmssd_ms == pytest.approx(math.sqrt(np.mean(d ** 2)), rel=1e-9)
    assert snap.features.sdnn_ms == pytest.approx(np.std(win, ddof=1), rel=1e-9)
    assert snap.features.pnn50 == pytest.approx(np.mean(np.abs(d) > 50), rel=1e-9)
    assert snap.mean_hr_bpm == pytest.approx(np.mean(60000 / win), rel=1e-9)
    assert snap.to_dict()["state"] == "valid"


def test_out_of_range_and_jumps_are_rejected() -> None:
    rr = steady(120)
    rr[60] = 2500.0  # too long (missed beat)
    rr[70] = 250.0  # too short (double count)
    rr[80] = rr[79] * 1.5  # +50 % jump
    hrv = RrHrv()
    t = feed(hrv, rr)
    beats = list(hrv._beats)
    rejected = [b.rr_ms for b in beats if not b.valid]
    assert 2500.0 in rejected and 250.0 in rejected and rr[80] in rejected
    snap = hrv.compute(t)
    assert snap.features is not None
    assert snap.quality.artifact_fraction > 0
    # RMSSD must not include the jumps around the rejected beats
    assert snap.features.rmssd_ms < 120


def test_no_successive_difference_across_a_rejected_beat() -> None:
    hrv = RrHrv()
    feed(hrv, [800.0] * 20 + [3000.0] + [900.0] * 20)
    beats = list(hrv._beats)
    i = next(k for k, b in enumerate(beats) if b.rr_ms == 3000.0)
    assert not beats[i].follows_previous  # the bad beat
    assert not beats[i + 1].follows_previous  # the beat after it: no 800 -> 900 pair across it


def test_silence_between_packets_breaks_the_chain() -> None:
    # The real watch goes quiet for seconds when the wrist sensor misses beats: packets keep
    # coming (seq in order, no loss) but carry no RR. Beats on both sides are not neighbours.
    tracker = SequenceTracker()
    hrv = RrHrv()
    t = 100.0
    for seq, rr in enumerate([(820,), (830,), (), (), (), (860,), (870,)]):
        t += 1.0
        hrv.add(tracker.accept(RrPacket(seq=seq, watch_ms=1000 * seq, hr_bpm=70, rr_ms=rr), t, t))
    follows = [b.follows_previous for b in hrv._beats]
    assert follows == [False, True, False, True]  # 830 -> 860 across 3 empty batches: no pair


def test_slow_heart_keeps_pairs_across_one_empty_batch() -> None:
    # At 50 bpm (RR 1200 ms) some 1 s batches legitimately contain no beat ending.
    tracker = SequenceTracker()
    hrv = RrHrv()
    t = 100.0
    for seq, rr in enumerate([(1200,), (), (1210,), (1190,)]):
        t += 1.0
        hrv.add(tracker.accept(RrPacket(seq=seq, watch_ms=1000 * seq, hr_bpm=50, rr_ms=rr), t, t))
    assert [b.follows_previous for b in hrv._beats] == [False, True, True]


def test_lost_packets_lower_quality_and_break_the_chain() -> None:
    rr = steady(120)
    hrv = RrHrv()
    t = feed(hrv, rr, drop_seqs={60, 61, 62, 63, 64, 65, 66})
    snap = hrv.compute(t)
    assert snap.quality.packet_loss_fraction > 0.05
    assert snap.quality.reasons & QualityReason.PACKET_LOSS
    assert snap.state in (HrvState.DEGRADED, HrvState.BAD)
    assert snap.quality.gaps >= 1


def test_warmup_then_valid() -> None:
    rr = steady(40)  # ~34 s of beats: not a full window yet
    hrv = RrHrv()
    t = feed(hrv, rr)
    snap = hrv.compute(t)
    assert snap.state == HrvState.WARMUP
    assert snap.features is None


def test_stale_when_the_watch_goes_quiet() -> None:
    hrv = RrHrv()
    t = feed(hrv, steady(120))
    snap = hrv.compute(t + 10.0)
    assert snap.state == HrvState.STALE
    assert snap.features is None and snap.mean_hr_bpm is None


def test_arm_movement_low_coverage_is_bad() -> None:
    # 20 good beats, then 40 s with no beats arriving (wrist sensor lost them), then 10 beats
    rr = steady(30)
    hrv = RrHrv()
    t = feed(hrv, rr, pause_after=20, pause_s=40.0)
    snap = hrv.compute(t)
    assert snap.quality.coverage < 0.6
    assert snap.state == HrvState.BAD
    assert snap.features is None


def test_app_restart_starts_a_new_warmup() -> None:
    rr = steady(150)
    hrv = RrHrv()
    t = feed(hrv, rr, restart_at=120)  # app restarted ~25 s before the end
    snap = hrv.compute(t)
    assert snap.state == HrvState.WARMUP
