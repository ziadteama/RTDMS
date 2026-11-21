"""Sliding packet-loss hysteresis for phone telemetry."""

from collections import deque
from collections.abc import Callable


class GarminLossMonitor:
    def __init__(self, set_throttle: Callable[[float], None]) -> None:
        self._outcomes: deque[bool] = deque(maxlen=60)
        self._set_throttle = set_throttle
        self.factor = 1.0

    def record(self, lost: bool) -> None:
        self._outcomes.append(lost)
        fraction = sum(self._outcomes) / len(self._outcomes)
        factor = self.factor
        if fraction > 0.05:
            factor = 0.5
        elif fraction < 0.02:
            factor = 1.0
        if factor != self.factor:
            self.factor = factor
            self._set_throttle(factor)
