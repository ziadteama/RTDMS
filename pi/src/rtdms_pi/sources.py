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


class PhysioSource(Protocol):
    def latest(self) -> PhysioReport | None: ...


class ScriptedFrameSource:
    def __init__(self, frames: list[FrameResult]) -> None:
        self.frames = tuple(frames)
        self._stop = threading.Event()

    def start(self, on_frame: Callable[[FrameResult], None]) -> None:
        self._stop.clear()
        for frame in self.frames:
            if self._stop.is_set():
                break
            on_frame(frame)

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
            calibrated=d.get("calibrated") if isinstance(d.get("calibrated"), bool) else None,
            calibration=d.get("calibration") if isinstance(d.get("calibration"), str) else None,
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
        args = stream.parse_args(
            [
                "--hybrid",
                "--drowsiness",
                "--face-backend",
                "litert",
                "--rotate",
                str(self.config.rotate),
            ]
        )

        def run() -> None:
            try:
                stream.pipeline_loop(args, self.shared)
            finally:
                on_frame(FrameResult(None, None, 0.0, None, False, self.clock()))

        self._thread = threading.Thread(target=run, daemon=True, name="vision")
        self._thread.start()

    def stop(self) -> None:
        if self.shared is not None:
            with self.shared.cond:
                self.shared.running = False
                self.shared.cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=5)


class GarminPhysioSource:
    """In-memory receiver only. P3 routes GATT writes here; no CSV or BLE server.

    The upstream receiver forces an asyncio queue; consume each accepted frame
    immediately on a private loop, without starting an asynchronous worker.
    Not verified on hardware.
    """

    def __init__(
        self,
        stale_s: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        receiver = importlib.import_module("dms_physiology.garmin_receiver")
        self.receiver = receiver.GarminRrReceiver(log=None, clock=clock, wall=wall)
        self._hrv = importlib.import_module("dms_physiology.garmin_hrv").RrHrv()
        self._enrich = importlib.import_module("dms_physiology.wesad_garmin").enrich_hrv_dict
        self._clock, self._wall, self._stale_s = clock, wall, stale_s
        self._lock = threading.Lock()
        self._last: Any = None

    def handle_write(self, raw: bytes) -> None:
        with self._lock:
            frame = self.receiver.handle_write(raw)
            if frame is not None:
                # The queue is already nonempty. Driving this coroutine directly
                # also works when P3 calls us inside its running asyncio loop.
                async def consume() -> None:
                    frames = self.receiver.frames()
                    try:
                        self._hrv.add(await anext(frames))
                    finally:
                        await frames.aclose()

                coro = consume()
                try:
                    coro.send(None)
                except StopIteration:
                    pass
                finally:
                    coro.close()
                self._last = frame

    def latest(self) -> PhysioReport | None:
        with self._lock:
            frame = self._last
            if frame is None or self._clock() - frame.rx_monotonic > self._stale_s:
                return None
            d = self._enrich(self._hrv.compute(self._clock(), self._wall()), None)
            return PhysioReport(
                {
                    "watch_connected": True,
                    "hr_bpm": frame.packet.hr_bpm,
                    "rr_ms": tuple(frame.packet.rr_ms),
                    "fatigue_probability": d["fatigue_probability"],
                    "hrv_state": d["state"],
                    "rmssd_ms": d["rmssd_ms"],
                    "quality": d["quality"],
                    "t": frame.rx_wall,
                },
                frame.rx_monotonic,
            )
