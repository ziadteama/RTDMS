"""Unresponsive-driver monitor: camera eye closure, then no response, then an emergency.

Pure state machine over injected time. The runtime calls `update()` once per decision with the
latest camera and wearable readings; fusion turns the result into the MAX alert and the
`alert.emergency` flag. Heart rate only *shortens* the wait when it is clearly abnormal at good
quality; a missing or normal heart rate never blocks or delays the emergency.

Clearing WAITING / EMERGENCY requires a real response: watch ACK, or eyes open long enough to
rule out blinks. Wrist motion is ignored (holding the phone must not cancel auto-SOS). Losing
the face is not a response: a slumped driver often drops out of the camera view.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EmergencyStage(StrEnum):
    NORMAL = "normal"
    WAITING = "waiting"  # eyes closed long enough; alarm at maximum, waiting for any response
    EMERGENCY = "emergency"  # nobody responded: the phone starts its SOS countdown


@dataclass(frozen=True, slots=True)
class EmergencyConfig:
    closure_trigger_s: float = 8.0  # continuous eye closure before the alarm escalates
    response_window_s: float = 10.0  # wait for a response when the watch is worn
    no_watch_window_s: float = 20.0  # longer wait on the camera alone
    abnormal_hr_window_s: float = 5.0  # shorter wait when heart rate is clearly abnormal
    eyes_open_clear_s: float = 1.5  # eyes must stay open this long to cancel waiting (not a blink)
    hr_low_bpm: float = 40.0
    hr_high_bpm: float = 150.0


@dataclass(frozen=True, slots=True)
class EmergencyInputs:
    closure_ms: float | None  # current continuous eye closure; None = no face / camera lost
    ack: bool = False  # "I'm OK" from the watch
    worn: bool | None = None  # watch worn and connected; None = unknown / no watch
    wrist_still_s: float | None = None  # seconds since the wrist last moved (not a cancel signal)
    hr_bpm: float | None = None
    hr_quality: str | None = None


@dataclass(frozen=True, slots=True)
class EmergencyStatus:
    stage: EmergencyStage
    reason: str | None = None


def _window_s(cfg: EmergencyConfig, x: EmergencyInputs) -> float:
    if x.hr_quality == "good" and x.hr_bpm is not None and (
        x.hr_bpm < cfg.hr_low_bpm or x.hr_bpm > cfg.hr_high_bpm
    ):
        return cfg.abnormal_hr_window_s
    return cfg.response_window_s if x.worn else cfg.no_watch_window_s


def _eyes_open(x: EmergencyInputs) -> bool:
    return x.closure_ms is not None and x.closure_ms <= 0


class EmergencyMonitor:
    def __init__(self, config: EmergencyConfig | None = None) -> None:
        self.config = config or EmergencyConfig()
        self._stage = EmergencyStage.NORMAL
        self._since = 0.0  # time the current stage began
        self._responded_at: float | None = None  # last ACK while eyes still shut
        self._eyes_open_since: float | None = None

    def reset(self) -> None:
        """Forget any closure in progress (e.g. while the driver calibrates with eyes shut)."""
        self._stage, self._since, self._responded_at = EmergencyStage.NORMAL, 0.0, None
        self._eyes_open_since = None

    @property
    def stage(self) -> EmergencyStage:
        return self._stage

    def update(self, now: float, x: EmergencyInputs) -> EmergencyStatus:
        cfg = self.config
        if _eyes_open(x):
            if self._eyes_open_since is None:
                self._eyes_open_since = now
        else:
            self._eyes_open_since = None

        closed_s = (x.closure_ms or 0.0) / 1000.0
        if self._stage is EmergencyStage.NORMAL:
            if self._responded_at is not None:
                # A response restarts the count: re-escalate only after a fresh full closure, so an
                # "I'm OK" with eyes still shut cannot flip the alarm back on at the next frame.
                closed_s = min(closed_s, now - self._responded_at)
            if not x.ack and closed_s >= cfg.closure_trigger_s:
                self._enter(EmergencyStage.WAITING, now)
        elif self._is_clear(x, now):
            # ACK with eyes still shut: remember when, so closure must build again from that time.
            # Sustained eyes open: full clear of that restart latch.
            self._responded_at = None if _eyes_open(x) else now
            self._enter(EmergencyStage.NORMAL, now)
        elif self._stage is EmergencyStage.WAITING and now - self._since >= _window_s(cfg, x):
            self._enter(EmergencyStage.EMERGENCY, now)
        return EmergencyStatus(self._stage, _REASONS[self._stage])

    def _is_clear(self, x: EmergencyInputs, now: float) -> bool:
        """Real cancel only: watch ACK, or eyes open longer than a blink. Not wrist motion."""
        if x.ack:
            return True
        return (
            self._eyes_open_since is not None
            and now - self._eyes_open_since >= self.config.eyes_open_clear_s
        )

    def _enter(self, stage: EmergencyStage, now: float) -> None:
        self._stage, self._since = stage, now


_REASONS = {
    EmergencyStage.NORMAL: None,
    EmergencyStage.WAITING: "driver not responding",
    EmergencyStage.EMERGENCY: "emergency: unresponsive",
}
