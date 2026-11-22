"""Map accepted watch frames onto Pi time without treating a replay as live data."""

from collections import deque

from .garmin_rr import Arrival, RrFrame

WINDOW_S = 300.0
LATE_S = 2.0
WATCH_MODULUS = 1 << 32


class WatchClock:
    """Sliding minimum-delay estimator, O(1) amortised per accepted frame.

    Arrival times must be nondecreasing. Drop DUPLICATE/LATE frames before calling add.
    A cold start (or outage longer than the window) cannot recover unknown buffering delay.
    Spread measures observed delay variation, not the unknown minimum transport latency.
    """

    def __init__(self, window_s: float = WINDOW_S) -> None:
        if window_s <= 0:
            raise ValueError("window_s must be positive")
        self.window_s = window_s
        self.reset()

    def reset(self) -> None:
        self._min: deque[tuple[float, float]] = deque()
        self._max: deque[tuple[float, float]] = deque()
        self._last_watch: int | None = None
        self._unwrapped = 0
        self.late_packets = 0

    @property
    def offset_ms(self) -> float | None:
        return self._min[0][1] if self._min else None

    @property
    def offset_spread_ms(self) -> float:
        return self._max[0][1] - self._min[0][1] if self._min else 0.0

    def add(self, frame: RrFrame) -> float:
        """Return sample time in Pi monotonic seconds; reset on NEW_SESSION."""
        if frame.arrival in (Arrival.DUPLICATE, Arrival.LATE):
            raise ValueError("WatchClock requires accepted frames")
        if frame.arrival == Arrival.NEW_SESSION:
            self.reset()
        watch = frame.packet.watch_ms
        if self._last_watch is None:
            self._unwrapped = watch
        else:
            # Signed modular difference also tolerates small backwards timer jitter.
            step = (watch - self._last_watch + WATCH_MODULUS // 2) % WATCH_MODULUS
            self._unwrapped += step - WATCH_MODULUS // 2
        self._last_watch = watch
        rx = frame.rx_monotonic
        offset = rx * 1000.0 - self._unwrapped
        cutoff = rx - self.window_s
        for queue in (self._min, self._max):
            while queue and queue[0][0] < cutoff:
                queue.popleft()
        while self._min and self._min[-1][1] >= offset:
            self._min.pop()
        while self._max and self._max[-1][1] <= offset:
            self._max.pop()
        self._min.append((rx, offset))
        self._max.append((rx, offset))
        placed = min(rx, (self._unwrapped + self._min[0][1]) / 1000.0)
        if rx - placed > LATE_S:
            self.late_packets += 1
        return placed
