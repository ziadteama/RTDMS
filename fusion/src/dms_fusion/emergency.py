"""Unresponsive-driver monitor: camera eye closure, then no response, then an emergency.

Pure state machine over injected time. The runtime calls `update()` once per decision with the
latest camera and wearable readings; fusion turns the result into the MAX alert and the
`alert.emergency` flag. Heart rate only *shortens* the wait when it is clearly abnormal at good
quality; a missing or normal heart rate never blocks or delays the emergency.
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
    hr_low_bpm: float = 40.0
    hr_high_bpm: float = 150.0


@dataclass(frozen=True, slots=True)
class EmergencyInputs:
    closure_ms: float | None  # current continuous eye closure; None = no face / camera lost
    ack: bool = False  # "I'm OK" from the watch
    worn: bool | None = None  # watch worn and connected; None = unknown / no watch
    wrist_still_s: float | None = None  # seconds since the wrist last moved
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


def _responded(x: EmergencyInputs, waited_s: float) -> bool:
    """A response is an ACK, open eyes, or (with the watch worn) the wrist moving while we wait.

    Losing the face is *not* a response: a slumped driver often drops out of the camera view.
    """
    if x.ack or (x.closure_ms is not None and x.closure_ms <= 0):
        return True
    return bool(x.worn) and x.wrist_still_s is not None and x.wrist_still_s < waited_s


class EmergencyMonitor:
    def __init__(self, config: EmergencyConfig | None = None) -> None:
        self.config = config or EmergencyConfig()
        self._stage = EmergencyStage.NORMAL
        self._since = 0.0  # time the current stage began

    @property
    def stage(self) -> EmergencyStage:
        return self._stage

    def update(self, now: float, x: EmergencyInputs) -> EmergencyStatus:
        cfg = self.config
        closed_s = (x.closure_ms or 0.0) / 1000.0
        if self._stage is EmergencyStage.NORMAL:
            if not x.ack and closed_s >= cfg.closure_trigger_s:
                self._enter(EmergencyStage.WAITING, now)
        elif _responded(x, now - self._since):
            self._enter(EmergencyStage.NORMAL, now)
        elif self._stage is EmergencyStage.WAITING and now - self._since >= _window_s(cfg, x):
            self._enter(EmergencyStage.EMERGENCY, now)
        return EmergencyStatus(self._stage, _REASONS[self._stage])

    def _enter(self, stage: EmergencyStage, now: float) -> None:
        self._stage, self._since = stage, now


_REASONS = {
    EmergencyStage.NORMAL: None,
    EmergencyStage.WAITING: "driver not responding",
    EmergencyStage.EMERGENCY: "emergency: unresponsive",
}
