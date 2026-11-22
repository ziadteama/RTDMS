"""Heart rate quality and personal context; no fatigue decision or emergency policy.

The watch produces ~1 s batches. Coverage uses occupied Pi-second bins in (now-30, now];
missing seconds count as missing HR, including startup. Split packets share one bin, with
its latest sample winning. Minimum good duration means 120 occupied good seconds, not the
span between two isolated readings. Quality is recorded at ingestion for baseline/trend.
"""

from collections import deque
from dataclasses import dataclass
from math import floor
from statistics import median
from typing import Literal

from .garmin_rr import Arrival, RrFrame

BUFFER_S = 600.0
COVERAGE_S = 30
MIN_COVERAGE = 0.8
STALE_S = 5.0
MOTION_BAD = 160  # provisional wrist-energy threshold until the hardware bench
JUMP_BPM = 25
JUMP_WINDOW_S = 1.0
BASELINE_S = 300.0  # first five session minutes only; never a rolling baseline
MIN_GOOD_S = 120  # distinct good one-second batches, excluding gaps and degraded samples
Quality = Literal["good", "degraded", "bad"]


@dataclass(frozen=True, slots=True)
class HrSnapshot:
    hr_bpm: int | None
    quality: Quality
    worn: bool | None
    hr_baseline_bpm: float | None
    hr_delta_bpm: float | None
    hr_trend_bpm_per_10min: float | None
    age_s: float | None


@dataclass(frozen=True, slots=True)
class HrSample:
    t: float
    bpm: int | None
    contact: bool | None
    motion: int | None
    bad: bool
    good: bool


class HrStream:
    """Pure stream with amortised O(1) adds and at most 600 bins per snapshot.

    Feed accepted frames in placed-time order. Small backwards clock corrections share
    the latest bin; a correction into an earlier bin is ignored. Snapshot now must be at
    least the last accepted sample time. Baseline survives eviction of the first 5 minutes.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._samples: deque[HrSample] = deque()
        self._coverage: deque[tuple[int, bool]] = deque()
        self._valid_seconds = 0
        self._baseline: dict[int, int] = {}  # bounded uint8 HR histogram
        self._baseline_count = 0
        self._start: float | None = None
        self._last_valid: tuple[float, int] | None = None

    def add(self, frame: RrFrame, t: float) -> None:
        if frame.arrival in (Arrival.DUPLICATE, Arrival.LATE):
            return
        if frame.arrival == Arrival.NEW_SESSION:
            self.reset()
        if self._start is None:
            self._start = t
        bucket = floor(t)
        if self._samples and bucket < floor(self._samples[-1].t):
            return
        p = frame.packet
        bad = p.contact is False or (p.motion is not None and p.motion >= MOTION_BAD)
        if p.hr_bpm is not None:
            if self._last_valid is not None:
                prev_t, prev_hr = self._last_valid
                bad |= 0 <= t - prev_t <= JUMP_WINDOW_S and abs(p.hr_bpm - prev_hr) > JUMP_BPM
            self._last_valid = (t, p.hr_bpm)
        self._trim_coverage(bucket)
        if self._coverage and self._coverage[-1][0] == bucket:
            self._valid_seconds -= self._coverage.pop()[1]
        valid = p.hr_bpm is not None
        self._coverage.append((bucket, valid))
        self._valid_seconds += valid
        if self._samples and floor(self._samples[-1].t) == bucket:
            bad |= self._samples[-1].bad
        good = not bad and valid and self._valid_seconds / COVERAGE_S >= MIN_COVERAGE
        sample = HrSample(t, p.hr_bpm, p.contact, p.motion, bad, good)
        if self._samples and floor(self._samples[-1].t) == bucket:
            self._update_baseline(self._samples.pop(), -1)
        self._samples.append(sample)
        self._update_baseline(sample, 1)
        while self._samples and self._samples[0].t <= t - BUFFER_S:
            self._samples.popleft()

    def _trim_coverage(self, bucket: int) -> None:
        while self._coverage and self._coverage[0][0] <= bucket - COVERAGE_S:
            self._valid_seconds -= self._coverage.popleft()[1]

    def _update_baseline(self, sample: HrSample, direction: int) -> None:
        if (self._start is not None and sample.t < self._start + BASELINE_S
                and sample.good and sample.bpm is not None):
            self._baseline[sample.bpm] = self._baseline.get(sample.bpm, 0) + direction
            self._baseline_count += direction

    def _baseline_bpm(self) -> float | None:
        if self._baseline_count < MIN_GOOD_S:
            return None
        # At most 300 values; the histogram keeps storage bounded across long sessions.
        return float(median([hr for hr, n in self._baseline.items() for _ in range(n)]))

    def snapshot(self, now: float) -> HrSnapshot:
        """Latest valid HR is retained even if stale; quality gates its use."""
        latest = self._samples[-1] if self._samples else None
        age = max(0.0, now - latest.t) if latest else None
        valid_seconds = sum(valid for bucket, valid in self._coverage
                            if floor(now) - COVERAGE_S < bucket <= floor(now))
        quality: Quality = "good"
        if latest is None or age is None or age > STALE_S or latest.bad:
            quality = "bad"
        elif valid_seconds / COVERAGE_S < MIN_COVERAGE:
            quality = "degraded"
        hr = self._last_valid[1] if self._last_valid else None
        baseline = self._baseline_bpm()
        delta = hr - baseline if hr is not None and baseline is not None else None
        return HrSnapshot(hr, quality, latest.contact if latest else None, baseline, delta,
                          self._trend(now), age)

    def _trend(self, now: float) -> float | None:
        good = [s for s in self._samples if now - BUFFER_S < s.t <= now and s.good]
        if len(good) < MIN_GOOD_S:
            return None
        # Centre times before regression to avoid cancellation at large Pi uptimes.
        origin = good[0].t
        xs = [s.t - origin for s in good]
        ys = [float(s.bpm) for s in good if s.bpm is not None]
        mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator == 0:
            return None
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
        return BUFFER_S * numerator / denominator
