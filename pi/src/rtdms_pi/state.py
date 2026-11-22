"""Immutable reports and synchronized runtime snapshots. Times are monotonic."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from dms_fusion import AlertPattern, FusionDecision


def freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class FaceReport:
    state: str = "unavailable"
    reasons: tuple[str, ...] = ()
    perclos: float | None = None
    openness: float | None = None
    blink_rate: float | None = None
    closure_ms: float | None = None
    face: bool = False
    calibrated: bool | None = None
    calibration: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))


@dataclass(frozen=True)
class PhoneReport:
    call: bool = False
    texting: bool = False
    phone_p: float | None = None
    phone_score: float | None = None
    sustained_phone_ms: float | None = None


@dataclass(frozen=True)
class PhysioReport:
    raw: Mapping[str, object]
    t: float  # reception time, never refreshed merely by reading latest()

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", freeze(dict(self.raw)))


@dataclass(frozen=True)
class DecisionSnapshot:
    pattern: AlertPattern = AlertPattern.NONE
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Snapshot:
    face: FaceReport | None = None
    phone: PhoneReport | None = None
    physio: PhysioReport | None = None
    face_t: float | None = None
    phone_t: float | None = None
    physio_t: float | None = None
    decision: DecisionSnapshot = field(default_factory=DecisionSnapshot)
    fps: float = 0.0
    temp_c: float | None = None
    camera_ok: bool = False
    t: float = 0.0


class RuntimeState:
    def __init__(
        self,
        stale_s: float = 2.0,
        physio_stale_s: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.stale_s = stale_s
        self.physio_stale_s = physio_stale_s
        self.clock = clock
        self._lock = threading.Lock()
        self._data = Snapshot()
        self._clock_offset_ms: int | None = None
        self._decision_listeners: list[Callable[[DecisionSnapshot], None]] = []

    def update_frame(
        self,
        face: FaceReport | None,
        phone: PhoneReport | None,
        fps: float,
        temp_c: float | None,
        camera_ok: bool,
        t: float,
    ) -> None:
        with self._lock:
            self._data = replace(
                self._data,
                face=face,
                phone=phone,
                face_t=t,
                phone_t=t,
                fps=fps,
                temp_c=temp_c,
                camera_ok=camera_ok,
            )

    def update_physio(self, report: PhysioReport | None) -> None:
        with self._lock:
            self._data = replace(self._data, physio=report, physio_t=report.t if report else None)

    def set_decision(self, decision: FusionDecision) -> None:
        with self._lock:
            changed = self._data.decision.pattern != decision.pattern
            current = DecisionSnapshot(decision.pattern, tuple(decision.reasons))
            self._data = replace(self._data, decision=current)
            if changed:
                for callback in self._decision_listeners:
                    callback(current)  # enqueue only; never perform transport I/O here

    def subscribe_decisions(self, callback: Callable[[DecisionSnapshot], None]) -> None:
        with self._lock:
            self._decision_listeners.append(callback)

    def unsubscribe_decisions(self, callback: Callable[[DecisionSnapshot], None]) -> None:
        with self._lock:
            self._decision_listeners.remove(callback)

    def snapshot(self) -> Snapshot:
        with self._lock:
            s = self._data
            now = self.clock()
            camera_ok = s.camera_ok and s.face_t is not None and 0 <= now - s.face_t <= self.stale_s
            physio = s.physio
            if physio is not None and not 0 <= now - physio.t <= self.physio_stale_s:
                physio = None
            return replace(
                s,
                t=now,
                camera_ok=camera_ok,
                physio=physio,
                face=s.face if camera_ok else None,
                phone=s.phone if camera_ok else None,
            )

    @property
    def clock_offset_ms(self) -> int | None:
        with self._lock:
            return self._clock_offset_ms

    def set_clock_offset(self, offset: int | None) -> None:
        with self._lock:
            self._clock_offset_ms = offset
