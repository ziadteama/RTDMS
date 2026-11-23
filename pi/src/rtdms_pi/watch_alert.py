"""Binary watch alert state and bounded, memory-only round-trip measurements."""

import math
import threading
from collections import deque

from dms_fusion import AlertPattern

_PATTERN_INDEX = {pattern: index for index, pattern in enumerate(AlertPattern)}


class WatchAlert:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = bytes((_PATTERN_INDEX[AlertPattern.NONE], 0))
        self._sent: dict[int, float] = {}
        self._rtts: deque[float] = deque(maxlen=200)

    def change(self, pattern: AlertPattern) -> bytes:
        with self._lock:
            seq = (self._value[1] + 1) % 256
            self._sent.pop(seq, None)
            self._value = bytes((_PATTERN_INDEX[pattern], seq))
            return self._value

    def read(self) -> bytes:
        with self._lock:
            return self._value

    def sent(self, value: bytes, now: float) -> None:
        with self._lock:
            self._sent.setdefault(value[1], now)  # keep-alives resend the same seq

    def echo(self, seq: int, arrival: float) -> None:
        with self._lock:
            sent = self._sent.pop(seq, None)
            if sent is not None and arrival >= sent:
                self._rtts.append((arrival - sent) * 1000)

    def diagnostics(self) -> dict[str, object]:
        with self._lock:
            samples = sorted(self._rtts)
        return {
            f"watch_alert_rtt_p{p}_ms": (
                round(samples[math.ceil(len(samples) * p / 100) - 1], 3) if samples else None
            )
            for p in (50, 95)
        }
