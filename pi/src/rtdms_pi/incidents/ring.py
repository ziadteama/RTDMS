"""Thread-safe ring buffer for camera frames and snapshot state."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Entry:
    t_mono: float
    t_wall: float
    jpeg: bytes | None
    status: dict[str, Any]
    alert: dict[str, Any]


class FrameRing:
    def __init__(
        self,
        seconds: float = 25.0,
        fps: float = 10.0,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        self.seconds = float(seconds)
        self.fps = float(fps)
        self.max_bytes = int(max_bytes)
        self._min_interval = (1.0 / self.fps) if self.fps > 0 else 0.0
        self._entries: deque[Entry] = deque()
        self._current_bytes: int = 0
        self._lock = threading.Lock()

    @staticmethod
    def _entry_bytes(entry: Entry) -> int:
        return (len(entry.jpeg) if entry.jpeg is not None else 0) + 256

    def push(self, entry: Entry) -> bool:
        with self._lock:
            if self._entries:
                last = self._entries[-1]
                dt = (
                    entry.t_mono - last.t_mono
                    if entry.t_mono != last.t_mono or entry.t_wall == last.t_wall
                    else entry.t_wall - last.t_wall
                )
                if dt < (self._min_interval - 1e-6):
                    return False

            entry_size = self._entry_bytes(entry)
            self._entries.append(entry)
            self._current_bytes += entry_size

            cutoff_wall = entry.t_wall - self.seconds
            cutoff_mono = entry.t_mono - self.seconds
            while len(self._entries) > 1:
                oldest = self._entries[0]
                is_expired = oldest.t_wall < cutoff_wall or (
                    entry.t_wall == 0.0 and oldest.t_mono < cutoff_mono
                )
                if is_expired:
                    removed = self._entries.popleft()
                    self._current_bytes -= self._entry_bytes(removed)
                else:
                    break

            while self._entries and self._current_bytes > self.max_bytes:
                removed = self._entries.popleft()
                self._current_bytes -= self._entry_bytes(removed)

            return True

    def window(self, t_start_mono: float, t_end_mono: float) -> list[Entry]:
        """Entries between two Pi monotonic times (the clock the phone offset maps onto)."""
        with self._lock:
            return [
                e
                for e in self._entries
                if t_start_mono <= e.t_mono <= t_end_mono
            ]

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def current_bytes(self) -> int:
        with self._lock:
            return self._current_bytes
