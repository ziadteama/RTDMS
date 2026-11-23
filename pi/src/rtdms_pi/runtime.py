"""Fusion owns thresholds; runtime owns input freshness and lifecycle."""

from __future__ import annotations

import signal
import threading
import time
from collections.abc import Callable, Mapping
from types import FrameType
from typing import Any

from dms_fusion import decide

from .buzzer import PatternPlayer
from .safety import Safety
from .sources import FrameResult, FrameSource, PhysioSource
from .state import RuntimeState
from .watch_alert import WatchAlert


class Runtime:
    def __init__(
        self,
        frame_source: FrameSource,
        physio_source: PhysioSource,
        player: PatternPlayer,
        state: RuntimeState,
        clock: Callable[[], float] = time.monotonic,
        tick_rate: float = 1.0,
        settings_provider: Callable[[], Mapping[str, Any]] | None = None,
        safety: Safety | None = None,
        watch_alert: WatchAlert | None = None,
    ) -> None:
        # Emergency monitor, break reminder and shadow score; None in unit tests that skip them.
        self.safety, self.watch_alert = safety, watch_alert
        self.frame_source, self.physio_source = frame_source, physio_source
        self.player, self.state, self.clock = player, state, clock
        self.settings_provider = settings_provider
        self._period = 1.0 / tick_rate
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._closed = False
        self._thread: threading.Thread | None = None

    def on_frame(self, frame: FrameResult) -> None:
        with self._lock:
            if self._stop.is_set():
                return
            self.state.update_frame(
                frame.face, frame.phone, frame.fps, frame.temp_c, frame.camera_ok, frame.t
            )
            self._decide()

    def _decide(self) -> None:
        self.state.update_physio(self.physio_source.latest())
        s = self.state.snapshot()
        face: dict[str, object] | None = {"state": s.face.state} if s.face and s.face.face else None
        phone: dict[str, object] | None = (
            {
                "call": s.phone.call,
                "texting": s.phone.texting,
                "phone_score": s.phone.phone_score,
                "sustained_phone_ms": s.phone.sustained_phone_ms,
            }
            if s.phone
            else None
        )
        physio: dict[str, object] | None = dict(s.physio.raw) if s.physio else None
        settings = self.settings_provider() if self.settings_provider is not None else None
        from .detector_gate import apply_settings

        face, phone, physio = apply_settings(settings, face, phone, physio)
        episode = 0
        if self.safety is None:
            decision = decide(face=face, phone=phone, physiology=physio)
        else:
            raw = decide(face=face, phone=phone, physiology=physio, **self.safety.inputs(s))
            out = self.safety.finish(raw, s)
            decision, episode = out.decision, out.episode
        self.state.set_decision(decision, episode)
        self.player.set_pattern(decision.pattern)

    def diagnostics(self) -> dict[str, object]:
        """Shadow counts and watch round-trip figures for health.physio_diag (BLE and HTTP)."""
        return {
            **(self.safety.diagnostics() if self.safety else {}),
            **(self.watch_alert.diagnostics() if self.watch_alert else {}),
        }

    def tick(self) -> None:
        with self._lock:
            if not self._stop.is_set():
                self._decide()

    def _watchdog(self) -> None:
        while not self._stop.wait(self._period):
            self.tick()

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("runtime is closed")
            if self._thread is not None:
                raise RuntimeError("runtime already started")
            self.frame_source.start(self.on_frame)
            self._thread = threading.Thread(target=self._watchdog, daemon=True, name="watchdog")
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
        try:
            self.frame_source.stop()
        finally:
            if self._thread is not None:
                self._thread.join(timeout=2)
            self.player.close()

    def run_forever(self) -> None:
        def terminate(signum: int, frame: FrameType | None) -> None:
            self._stop.set()

        previous = {sig: signal.signal(sig, terminate) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            self.start()
            self._stop.wait()
        finally:
            self.stop()
            for sig, handler in previous.items():
                signal.signal(sig, handler)
