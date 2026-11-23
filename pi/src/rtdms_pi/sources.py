"""Frame and watch adapters. Hardware paths are not verified on hardware."""

from __future__ import annotations

import importlib
import math
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from .config import RuntimeConfig
from .garmin_source import GarminPhysioSource as GarminPhysioSource
from .state import FaceReport, PhoneReport, PhysioReport


@dataclass(frozen=True)
class FrameResult:
    face: FaceReport | None
    phone: PhoneReport | None
    fps: float
    temp_c: float | None
    camera_ok: bool
    t: float


class FrameSource(Protocol):
    def start(self, on_frame: Callable[[FrameResult], None]) -> None: ...
    def stop(self) -> None: ...
    def start_calibration(self) -> None: ...
    def apply_phone_calibration(self, profile: dict[str, Any]) -> None: ...


class PhysioSource(Protocol):
    def latest(self) -> PhysioReport | None: ...


class ScriptedFrameSource:
    def __init__(self, frames: list[FrameResult]) -> None:
        self.frames = tuple(frames)
        self.calibration_calls = 0
        self.phone_profiles: list[dict[str, Any]] = []
        self._stop = threading.Event()

    def start(self, on_frame: Callable[[FrameResult], None]) -> None:
        self._stop.clear()
        for frame in self.frames:
            if self._stop.is_set():
                break
            on_frame(frame)

    def start_calibration(self) -> None:
        self.calibration_calls += 1

    def apply_phone_calibration(self, profile: dict[str, Any]) -> None:
        self.phone_profiles.append(dict(profile))

    def stop(self) -> None:
        self._stop.set()


class NullPhysioSource:
    def latest(self) -> None:
        return None


def number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def map_status(status: dict[str, Any], t: float) -> FrameResult:
    d = status.get("drowsiness")
    visible = status.get("face") is True
    face = FaceReport()
    if isinstance(d, dict):
        visible = visible and d.get("face") is True
        reasons = d.get("reasons", ())
        calibrated = d.get("calibrated") if isinstance(d.get("calibrated"), bool) else None
        msg = d.get("message")
        is_failed = isinstance(msg, str) and msg.startswith("calibration failed")
        is_calibrated = calibrated is True or msg == "calibrated (phone)"
        # "calibrating" first: a new Pi-camera run must be visible even over an older profile, so
        # the phone can see calibrating -> ok / failed (Bluetooth status has no free-text message).
        if msg == "calibrating":
            calibration: str | None = "calibrating"
        elif is_failed:
            calibration = "failed"
        else:
            calibration = "ok" if is_calibrated else None
        face = FaceReport(
            state=str(d.get("state", "unavailable")) if visible else "unavailable",
            reasons=tuple(r for r in reasons if isinstance(r, str))
            if isinstance(reasons, (list, tuple))
            else (),
            perclos=number(d.get("perclos")),
            openness=number(d.get("openness")),
            blink_rate=number(d.get("blink_rate")),
            closure_ms=number(d.get("closure_ms")),
            face=visible,
            calibrated=calibrated,
            calibration=calibration,
        )
    hybrid = status.get("hybrid")
    phone = None
    if isinstance(hybrid, dict) and visible and hybrid.get("face", True) is True:
        # p is the winning action confidence, not necessarily a phone score.
        phone = PhoneReport(
            call=hybrid.get("call") is True,
            texting=hybrid.get("texting") is True,
            phone_p=number(hybrid.get("p"))
            if hybrid.get("action") in ("call", "texting")
            else None,
            phone_score=number(hybrid.get("phone_score")),
            sustained_phone_ms=number(hybrid.get("sustained_phone_ms")),
        )
    return FrameResult(
        face, phone, number(status.get("fps")) or 0.0, number(status.get("temp_c")), True, t
    )


# The production camera configuration (models/distraction start_stream.sh on the Pi): face mesh
# drowsiness + v2 hybrid phone alerts, no box detector, texting alerts off.
CAMERA_ARGS = ("--no-rectify", "--roi", "full", "--drowsiness", "--no-texting", "--hybrid",
               "--no-detect")


class StreamPipelineSource:
    """Pi-only adapter; not verified on hardware. Shared remains available for MJPEG."""

    def __init__(self, config: RuntimeConfig, clock: Callable[[], float] = time.monotonic) -> None:
        self.config, self.clock = config, clock
        self.shared: Any = None  # boundary to the untyped upstream script
        self._thread: threading.Thread | None = None
        self._last: float | None = None

    @property
    def camera_ok(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._last is not None
            and self.clock() - self._last <= self.config.stale_s
        )

    def start(self, on_frame: Callable[[FrameResult], None]) -> None:
        if self._thread is not None:
            raise RuntimeError("source already started")
        scripts = str(self.config.repo_root / "models/distraction/scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        stream = importlib.import_module("stream")
        # Upstream Shared is untyped and only importable with the vision stack.
        if TYPE_CHECKING:

            class Shared:
                pass
        else:
            Shared = stream.Shared
        owner = self

        class _HookedShared(Shared):
            _ready = False

            @property
            def status(self) -> dict[str, Any]:
                return self._status

            @status.setter
            def status(self, value: dict[str, Any]) -> None:
                self._status = value
                if self._ready:
                    owner._last = owner.clock()
                    on_frame(map_status(value, owner._last))

        self.shared = _HookedShared()
        self.shared._ready = True
        args = stream.parse_args([*CAMERA_ARGS, "--rotate", str(self.config.rotate)])
        if self.config.stream_port:
            # Same page, MJPEG, /status and /calibrate as the standalone camera service; frames are
            # only encoded while a viewer is connected.
            server = stream.DualStackServer(
                (self.config.host, self.config.stream_port), stream.make_handler(self.shared)
            )
            threading.Thread(target=server.serve_forever, daemon=True, name="stream-http").start()

        def run() -> None:
            try:
                stream.pipeline_loop(args, self.shared)
            finally:
                on_frame(FrameResult(None, None, 0.0, None, False, self.clock()))

        self._thread = threading.Thread(target=run, daemon=True, name="vision")
        self._thread.start()

    def start_calibration(self) -> None:
        if self.shared is None:
            raise RuntimeError("source not started")
        self.shared.calibrate = True

    def apply_phone_calibration(self, profile: dict[str, Any]) -> None:
        if self.shared is None:
            raise RuntimeError("source not started")
        self.shared.submit_phone_calibration(profile)

    def stop(self) -> None:
        if self.shared is not None:
            with self.shared.cond:
                self.shared.running = False
                self.shared.cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=5)
