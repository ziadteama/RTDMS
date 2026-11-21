"""Nonblocking tone backends and a separately scheduled pattern worker."""

from __future__ import annotations

import importlib
import threading
import time
from collections.abc import Callable
from typing import Protocol

from dms_fusion import AlertPattern


class BuzzerBackend(Protocol):
    """play starts a tone immediately; PatternPlayer owns timing and calls off."""

    def play(self, tone_hz: int, seconds: float) -> None: ...
    def off(self) -> None: ...
    def close(self) -> None: ...


class VibrationBackend(Protocol):
    def on(self) -> None: ...
    def off(self) -> None: ...
    def close(self) -> None: ...


class GpioBuzzer:
    """gpiozero TonalBuzzer; not verified on hardware."""

    def __init__(self, pin: int = 18) -> None:
        self._buzzer = importlib.import_module("gpiozero").TonalBuzzer(pin)
        self._tone = importlib.import_module("gpiozero.tones").Tone

    def play(self, tone_hz: int, seconds: float) -> None:
        self._buzzer.play(self._tone(frequency=tone_hz))

    def off(self) -> None:
        self._buzzer.stop()

    def close(self) -> None:
        self.off()
        self._buzzer.close()


class GpioVibration:
    """Optional digital vibration output; not verified on hardware."""

    def __init__(self, pin: int) -> None:
        self._device = importlib.import_module("gpiozero").OutputDevice(pin)

    def on(self) -> None:
        self._device.on()

    def off(self) -> None:
        self._device.off()

    def close(self) -> None:
        self.off()
        self._device.close()


class SilentBuzzer:
    def play(self, tone_hz: int, seconds: float) -> None:
        pass

    def off(self) -> None:
        pass

    def close(self) -> None:
        pass


class ConsoleBuzzer(SilentBuzzer):
    def play(self, tone_hz: int, seconds: float) -> None:
        print(f"buzzer: {tone_hz} Hz ({seconds:g} s)", flush=True)


class RecordingBuzzer(SilentBuzzer):
    def __init__(self) -> None:
        self.events: list[tuple[str, int, float]] = []

    def play(self, tone_hz: int, seconds: float) -> None:
        self.events.append(("play", tone_hz, seconds))

    def off(self) -> None:
        self.events.append(("off", 0, 0.0))

    def close(self) -> None:
        self.events.append(("close", 0, 0.0))


class PatternPlayer:
    def __init__(
        self,
        backend: BuzzerBackend,
        vibration: VibrationBackend | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], object] | None = None,
        *,
        autostart: bool = True,
    ) -> None:
        self.backend, self.vibration, self.clock = backend, vibration, clock
        self._stop = threading.Event()
        self._closed = False
        self._wake = threading.Event()
        self._sleep = sleep or self._wake.wait
        self._lock = threading.Lock()
        self._live = AlertPattern.NONE
        self._override: tuple[AlertPattern, float] | None = None
        self._active: AlertPattern | None = None
        self._epoch = clock()
        self._phase: int | None = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="patterns")
        if autostart:
            self._thread.start()

    def set_pattern(self, pattern: AlertPattern) -> None:
        with self._lock:
            if self._stop.is_set() or self._live == pattern:
                return
            self._live = pattern
        self._wake.set()

    def test_pattern(self, pattern: AlertPattern, seconds: float = 2.0) -> None:
        if not 0 < seconds <= 10:
            raise ValueError("test duration must be between 0 and 10 seconds")
        with self._lock:
            if self._stop.is_set():
                return
            self._override = (pattern, self.clock() + seconds)
            self._active = None
        self._wake.set()

    def step(self) -> None:
        """One scheduler step, also usable with a fake clock without a worker."""
        with self._lock:
            if self._stop.is_set():
                return
            now = self.clock()
            if self._override is not None and now >= self._override[1]:
                self._override = None
                self._active = None
            pattern = self._override[0] if self._override is not None else self._live
            if pattern != self._active:
                self.backend.off()
                if self.vibration:
                    self.vibration.off()
                    if pattern in (AlertPattern.MAX, AlertPattern.REPEATED):
                        self.vibration.on()
                self._active, self._epoch, self._phase = pattern, now, None
            elapsed = now - self._epoch
            tone, duration, phase = 0, 0.0, 0
            if pattern == AlertPattern.SHORT_BEEP:
                cycle = int(elapsed / 3)
                on = elapsed - cycle * 3 < 0.25
                phase, tone, duration = cycle * 2 + (0 if on else 1), 800 if on else 0, 0.25
            elif pattern == AlertPattern.REPEATED:
                phase = int(elapsed / 0.25)
                tone, duration = (800 if phase % 2 == 0 else 0), 0.25
            elif pattern == AlertPattern.CONTINUOUS:
                tone, duration = 1200, float("inf")
            elif pattern == AlertPattern.MAX:
                phase = int(elapsed / 0.15)
                tone, duration = (1200 if phase % 2 == 0 else 1800), 0.15
            if phase != self._phase:
                self._phase = phase
                if tone:
                    self.backend.play(tone, duration)
                else:
                    self.backend.off()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self._wake.clear()
                self.step()
                self._sleep(0.01)
        finally:
            with self._lock:
                if not self._closed:
                    self.backend.off()
                    if self.vibration:
                        self.vibration.off()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        with self._lock:
            self.backend.off()
            self.backend.close()
            if self.vibration:
                self.vibration.off()
                self.vibration.close()
