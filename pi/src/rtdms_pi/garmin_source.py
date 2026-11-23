"""Synchronous, memory-only adapter around the physiology stream primitives."""

import threading
import time
from collections.abc import Callable
from dataclasses import replace

from dms_physiology.garmin_hrv import UPDATE_S, HrvSnapshot, RrHrv
from dms_physiology.garmin_rr import Arrival, RrCodecError, RrFrame, SequenceTracker, decode
from dms_physiology.hr_stream import HrSnapshot, HrStream
from dms_physiology.watch_clock import WatchClock

from .state import PhysioReport

# Provisional wrist-energy threshold; requires hardware calibration before policy use.
MOTION_ACTIVE = 40


class GarminPhysioSource:
    def __init__(
        self,
        stale_s: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self.tracker = SequenceTracker()
        self.watch_clock = WatchClock()
        self.decode_errors = 0
        self._hr, self._hrv = HrStream(), RrHrv()
        self._clock, self._wall, self._stale_s = clock, wall, stale_s
        self._lock = threading.Lock()
        self._last: RrFrame | None = None
        self._placed = 0.0
        self._motion_t: float | None = None
        self._ack_t: float | None = None
        self._hr_snapshot: HrSnapshot | None = None
        self._hrv_snapshot: HrvSnapshot | None = None
        self._snapshot_at = self._hrv_at = float("-inf")

    def handle_write(self, raw: bytes) -> None:
        with self._lock:
            try:
                packet = decode(raw)
            except RrCodecError:
                self.decode_errors += 1
                return
            frame = self.tracker.accept(packet, self._clock(), self._wall())
            if frame.arrival in (Arrival.DUPLICATE, Arrival.LATE):
                return
            t = self.watch_clock.add(frame)
            self._hr.add(frame, t)
            self._hrv.add(replace(frame, rx_monotonic=t))
            if frame.arrival == Arrival.NEW_SESSION or self._was_stale(frame.rx_monotonic):
                self._motion_t = self._ack_t = None
                self._snapshot_at = self._hrv_at = float("-inf")  # recompute at once
            if packet.motion is None:
                self._motion_t = None
            elif packet.motion >= MOTION_ACTIVE or self._motion_t is None:
                # A session beginning at rest has only been observed still since now.
                self._motion_t = t
            if packet.ack:
                self._ack_t = t
            self._last, self._placed = frame, t

    def _was_stale(self, now: float) -> bool:
        return self._last is not None and now - self._last.rx_monotonic > self._stale_s

    def latest(self) -> PhysioReport | None:
        """Fresh report on every call; only the HR (1 Hz) and PRV (5 s) maths is cached.

        The runtime calls this per camera frame, so ACK, echo, motion and ages must never be
        served from a cache, while the stream statistics need not be recomputed 15 times a second.
        """
        with self._lock:
            now, frame = self._clock(), self._last
            if frame is None or now - frame.rx_monotonic > self._stale_s:
                return None
            if self._hr_snapshot is None or now - self._snapshot_at >= 1.0:
                self._hr_snapshot, self._snapshot_at = self._hr.snapshot(now), now
            if self._hrv_snapshot is None or now - self._hrv_at >= UPDATE_S:
                self._hrv_snapshot, self._hrv_at = self._hrv.compute(now), now
            hr, hrv = self._hr_snapshot, self._hrv_snapshot
            return PhysioReport(
                {
                    "watch_connected": True,
                    "worn": hr.worn,
                    "hr_bpm": hr.hr_bpm,
                    "quality": hr.quality,
                    "hr_baseline_bpm": hr.hr_baseline_bpm,
                    "hr_delta_bpm": hr.hr_delta_bpm,
                    "hr_trend_bpm_per_10min": hr.hr_trend_bpm_per_10min,
                    "rr_ms": frame.packet.rr_ms,
                    "rmssd_ms": hrv.features.rmssd_ms if hrv.features else None,
                    "hrv_state": hrv.state.value,
                    "motion": frame.packet.motion,
                    "wrist_still_s": None
                    if self._motion_t is None
                    else max(0.0, now - self._motion_t),
                    "ack_age_s": None if self._ack_t is None else max(0.0, now - self._ack_t),
                    "echo_seq": frame.packet.echo_seq,
                },
                self._placed,
            )

    def diagnostics(self) -> dict[str, object]:
        with self._lock:
            return {
                "watch_offset_spread_ms": self.watch_clock.offset_spread_ms,
                "late_packets": self.watch_clock.late_packets,
            }
