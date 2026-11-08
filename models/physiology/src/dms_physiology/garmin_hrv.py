"""HRV from the Garmin watch's RR intervals: artifact filter, 60 s window, features, quality.

Pipeline (numpy only, a few hundred beats at most, so it costs microseconds per update):

    RrFrame (garmin_rr) -> RrHrv.add()      one packet: 0-5 RR intervals + Pi receive time
                        -> artifact filter   keep 300-2000 ms; reject a jump > 20% from the
                                             previous accepted beat
                        -> beat buffer       last BUFFER_S seconds of beats
    every 5 s           -> RrHrv.compute()   60 s window: mean HR, RMSSD, SDNN, pNN50 (+ the
                                             rest of FeatureSnapshot) and a quality report

Rules that keep the numbers honest:
- Successive differences (RMSSD, pNN50) are only taken between beats that really followed each
  other: never across a rejected beat, a lost packet, a Bluetooth gap or a new session.
- Beat times come from the Pi clock (the packet's receive time, minus the later beats of the
  same packet), so features line up with camera frames. The watch clock is never used for time.
- Bad input gives no HRV numbers (features = None), never a guess. Fusion decides what to do.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from .config import QualityConfig
from .features import FeatureSnapshot
from .garmin_rr import Arrival, RrFrame
from .types import QualityReason, QualityState

WINDOW_S = 60.0  # feature window
UPDATE_S = 5.0  # how often the caller should compute (the service runs compute() on a timer)
BUFFER_S = 120.0  # beats kept in memory
STALE_S = 5.0  # no packet for this long -> STALE
MIN_RR_MS, MAX_RR_MS = 300.0, 2000.0  # 30-200 bpm
MAX_JUMP = 0.20  # reject a beat more than 20% away from the previous accepted beat
MIN_BEATS = 30  # fewer accepted beats in the window -> not enough for HRV
MIN_PAIRS = 10  # fewer true successive beat pairs -> no RMSSD / pNN50
# The watch hands over beats once a second and goes silent when the wrist sensor misses beats
# (in a 5-min resting test about half the 1 s batches came with no RR at all). Two beats on
# either side of a silence are NOT neighbours. A beat follows the previous one only if the time
# between their packets fits: elapsed <= this RR + one batch period + delivery jitter.
BATCH_S, JITTER_S = 1.0, 0.15
MIN_COVERAGE_GOOD, MIN_COVERAGE_DEGRADED = 0.8, 0.6  # accepted beat time / window length


@dataclass(frozen=True, slots=True)
class Beat:
    """One RR interval as received, with the filter's decision."""

    t: float  # Pi monotonic time at the END of this beat
    rr_ms: float
    valid: bool
    follows_previous: bool  # the previous beat in the buffer is really the one just before it


class HrvState(StrEnum):
    WARMUP = "warmup"  # less than one window of data since the session started
    VALID = "valid"  # quality GOOD
    DEGRADED = "degraded"  # usable with caution
    BAD = "bad"  # no HRV numbers
    STALE = "stale"  # no data from the watch for STALE_S (watch away, app closed)


@dataclass(frozen=True, slots=True)
class RrQuality:
    """Why a window can or cannot be trusted. Gates outputs; never a model feature."""

    state: QualityState
    reasons: QualityReason
    packet_loss_fraction: float  # lost packets / (received + lost) in the window
    artifact_fraction: float  # rejected beats / all beats in the window
    coverage: float  # accepted beat time / window length (low = watch off, arm moving)
    valid_beats: int
    gaps: int  # places in the window where the beat stream broke


@dataclass(frozen=True, slots=True)
class HrvSnapshot:
    """What RrHrv publishes every UPDATE_S: timestamped, quality-gated."""

    t_monotonic: float  # Pi monotonic time of the computation (end of the window)
    t_wall: float
    state: HrvState
    mean_hr_bpm: float | None  # kept when there are enough beats even if HRV is not trusted
    features: FeatureSnapshot | None  # None unless state is VALID or DEGRADED
    quality: RrQuality

    def to_dict(self) -> dict[str, object]:
        f = self.features
        q = self.quality
        return {
            "t_monotonic": round(self.t_monotonic, 3), "t_wall": round(self.t_wall, 3),
            "state": self.state.value,
            "mean_hr_bpm": None if self.mean_hr_bpm is None else round(self.mean_hr_bpm, 1),
            "rmssd_ms": None if f is None else round(f.rmssd_ms, 1),
            "sdnn_ms": None if f is None else round(f.sdnn_ms, 1),
            "pnn50": None if f is None else round(f.pnn50, 3),
            "quality": q.state.value, "quality_reasons": int(q.reasons),
            "packet_loss": round(q.packet_loss_fraction, 3),
            "artifacts": round(q.artifact_fraction, 3), "coverage": round(q.coverage, 2),
            "valid_beats": q.valid_beats, "gaps": q.gaps,
        }


class RrHrv:
    """Feeds on RrFrames, computes a 60 s HRV window on demand. Not thread-safe by itself:
    call add() and compute() from one thread (the receiver's event loop)."""

    def __init__(self, quality: QualityConfig | None = None, window_s: float = WINDOW_S) -> None:
        self.q = quality or QualityConfig()
        self.window_s = window_s
        self._beats: deque[Beat] = deque()
        self._packets: deque[tuple[float, int]] = deque()  # (rx time, lost before it)
        self._last_valid_rr: float | None = None  # previous accepted beat, for the 20% rule
        self._last_rx: float | None = None
        self._last_beat_rx: float | None = None  # receive time of the packet with the last beat
        self._last_wall = 0.0
        self._session_start: float | None = None
        self._session = 0

    def add(self, frame: RrFrame) -> None:
        """One accepted packet from the receiver (DUPLICATE / LATE never reach here)."""

        if frame.arrival == Arrival.DUPLICATE or frame.arrival == Arrival.LATE:
            return
        if frame.session != self._session:  # app restarted: start over
            self._session = frame.session
            self._session_start = frame.rx_monotonic
            self._last_valid_rr = None
        broken = frame.gap_before or frame.arrival == Arrival.NEW_SESSION
        if broken:
            self._last_valid_rr = None
        self._packets.append((frame.rx_monotonic, frame.lost_before))
        self._last_rx, self._last_wall = frame.rx_monotonic, frame.rx_wall

        # The packet arrived right after its last beat ended; earlier beats ended before that.
        rr = [float(x) for x in frame.packet.rr_ms]
        t_end = frame.rx_monotonic
        ends = []
        for value in reversed(rr):
            ends.append(t_end)
            t_end -= value / 1000.0
        ends.reverse()
        if rr and self._last_beat_rx is not None and not broken:
            # first beat of this packet vs the last beat we have: did beats go missing between?
            elapsed = frame.rx_monotonic - self._last_beat_rx
            if elapsed > rr[0] / 1000.0 + BATCH_S + JITTER_S:
                broken = True
        for i, (value, t) in enumerate(zip(rr, ends, strict=True)):
            valid = self._accept(value)
            prev = self._beats[-1] if self._beats else None
            follows = prev is not None and prev.valid and valid and not (broken and i == 0)
            self._beats.append(Beat(t, value, valid, follows))
        if rr:
            self._last_beat_rx = frame.rx_monotonic
        self._trim(frame.rx_monotonic)

    def _accept(self, rr_ms: float) -> bool:
        """The artifact filter: plausible range, then at most a 20% step from the last good
        beat. A rejected beat does not move the reference, so one bad beat cannot drag the
        filter away from the real rhythm."""
        if not MIN_RR_MS <= rr_ms <= MAX_RR_MS:
            return False
        ref = self._last_valid_rr
        if ref is not None and abs(rr_ms - ref) > MAX_JUMP * ref:
            return False
        self._last_valid_rr = rr_ms
        return True

    def _trim(self, now: float) -> None:
        while self._beats and now - self._beats[0].t > BUFFER_S:
            self._beats.popleft()
        while self._packets and now - self._packets[0][0] > BUFFER_S:
            self._packets.popleft()

    def compute(self, now: float, now_wall: float | None = None) -> HrvSnapshot:
        """Features and quality for the window ending at `now` (Pi monotonic seconds)."""

        if now_wall is not None:
            wall = now_wall
        else:  # wall time of the last packet, moved forward by the monotonic time since
            wall = self._last_wall + (now - (self._last_rx or now))
        start = now - self.window_s
        beats = [b for b in self._beats if start < b.t <= now]
        packets = [p for p in self._packets if start < p[0] <= now]

        valid = np.asarray([b.rr_ms for b in beats if b.valid], dtype=float)
        # successive differences only between beats that truly followed each other
        diffs = np.asarray([beats[i].rr_ms - beats[i - 1].rr_ms for i in range(1, len(beats))
                            if beats[i].follows_previous], dtype=float)
        lost = sum(p[1] for p in packets)
        loss = lost / (len(packets) + lost) if packets or lost else 0.0
        artifacts = 1.0 - valid.size / len(beats) if beats else 0.0
        coverage = min(1.0, float(valid.sum()) / 1000.0 / self.window_s) if valid.size else 0.0
        gaps = sum(1 for i in range(1, len(beats)) if not beats[i].follows_previous)

        reasons = QualityReason.NONE
        if loss > self.q.max_good_packet_loss_fraction:
            reasons |= QualityReason.PACKET_LOSS
        if artifacts > self.q.max_good_artifact_fraction:
            reasons |= QualityReason.ARTIFACTS
        if valid.size < MIN_BEATS or coverage < MIN_COVERAGE_GOOD:
            reasons |= QualityReason.INSUFFICIENT_BEATS
        enough = valid.size >= MIN_BEATS and diffs.size >= MIN_PAIRS
        if enough and coverage >= MIN_COVERAGE_GOOD and reasons == QualityReason.NONE:
            qstate = QualityState.GOOD
        elif (enough and coverage >= MIN_COVERAGE_DEGRADED
              and loss <= self.q.max_degraded_packet_loss_fraction
              and artifacts <= self.q.max_degraded_artifact_fraction):
            qstate = QualityState.DEGRADED
        else:
            qstate = QualityState.BAD
        quality = RrQuality(qstate, reasons, loss, artifacts, coverage, int(valid.size), gaps)

        mean_hr = float(np.mean(60_000.0 / valid)) if valid.size >= 10 else None
        stale = self._last_rx is None or now - self._last_rx > STALE_S
        warming = self._session_start is None or now - self._session_start < self.window_s
        if stale:
            state = HrvState.STALE
        elif warming:
            state = HrvState.WARMUP
        else:
            state = {QualityState.GOOD: HrvState.VALID, QualityState.DEGRADED: HrvState.DEGRADED,
                     QualityState.BAD: HrvState.BAD}[qstate]
        features = None
        if state in (HrvState.VALID, HrvState.DEGRADED):
            features = _features(valid, diffs, len(beats))
        return HrvSnapshot(now, wall, state, None if stale else mean_hr, features, quality)


def _features(valid: np.ndarray, diffs: np.ndarray, total_beats: int) -> FeatureSnapshot:
    """Time-domain features on accepted beats (no interpolation of rejected ones)."""
    rmssd = float(np.sqrt(np.mean(np.square(diffs)))) if diffs.size else math.nan
    sdnn = float(np.std(valid, ddof=1))
    pnn50 = float(np.mean(np.abs(diffs) > 50.0)) if diffs.size else math.nan
    hr = 60_000.0 / valid
    # bpm per minute: regress HR on cumulative beat time
    t_min = np.cumsum(valid) / 60_000.0
    slope = float(np.polyfit(t_min, hr, 1)[0]) if valid.size >= 3 else 0.0
    return FeatureSnapshot(
        mean_hr_bpm=float(np.mean(hr)),
        hr_slope_bpm_per_min=slope,
        median_ibi_ms=float(np.median(valid)),
        rmssd_ms=rmssd,
        sdnn_ms=sdnn,
        pnn50=pnn50,
        cvnn=sdnn / float(np.mean(valid)),
        valid_interval_count=int(valid.size),
        artifact_fraction=0.0 if total_beats == 0 else 1.0 - valid.size / total_beats,
    )
