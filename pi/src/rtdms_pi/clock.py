"""Phone epoch alignment; all durations remain on the Pi monotonic clock."""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable

_sync_lock = threading.Lock()
_sync_attempted = False


class PhoneClock:
    def __init__(
        self,
        monotonic: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        set_system_clock: Callable[[float], None] | None = None,
    ) -> None:
        self.monotonic, self.wall = monotonic, wall
        self._set_system_clock = set_system_clock
        self._offsets: deque[float] = deque(maxlen=10)
        self._lock = threading.Lock()

    def on_clock_write(self, pi_mono_ms: float, phone_ms: float) -> None:
        with self._lock:
            self._offsets.append(pi_mono_ms - phone_ms)
        self._sync(phone_ms / 1000)

    def _sync(self, phone_s: float) -> None:
        global _sync_attempted
        setter = self._set_system_clock
        if setter is None:
            return
        with _sync_lock:
            if _sync_attempted or abs(phone_s - self.wall()) <= 2:
                return
            _sync_attempted = True
        try:
            setter(phone_s)
        except Exception:
            logging.getLogger(__name__).warning("System clock sync failed")

    @property
    def offset_ms(self) -> float | None:
        with self._lock:
            return min(self._offsets) if self._offsets else None

    def payload_t(self, mono_s: float) -> tuple[float, str]:
        offset = self.offset_ms
        if offset is None:
            return self.wall(), "pi"
        return (mono_s * 1000 - offset) / 1000, "phone"
