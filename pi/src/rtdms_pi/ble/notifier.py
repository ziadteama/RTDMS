"""Clock-driven telemetry schedule, independently testable by step()."""

import asyncio
import math
from collections.abc import Callable
from queue import Empty, SimpleQueue

from ..payloads import alert_payload, physio_payload, status_payload
from ..state import DecisionSnapshot, RuntimeState
from .uuids import Char


class Notifier:
    def __init__(
        self,
        state: RuntimeState,
        clock: Callable[[], float],
        emit: Callable[[Char, str, dict[str, object]], None],
    ) -> None:
        self.state, self.clock, self.emit = state, clock, emit
        self.factor = 1.0
        self._last = {char: float("-inf") for char in (Char.ALERT, Char.STATUS, Char.PHYSIO)}
        self._pattern: str | None = None
        self._changes: SimpleQueue[DecisionSnapshot] = SimpleQueue()
        self.state.subscribe_decisions(self._changes.put)

    def close(self) -> None:
        self.state.unsubscribe_decisions(self._changes.put)

    def _drain_changes(self, now: float) -> bool:
        emitted = False
        while True:
            try:
                decision = self._changes.get_nowait()
            except Empty:
                return emitted
            self.emit(Char.ALERT, "alert", alert_payload(decision, now))
            emitted = True
            self._last[Char.ALERT], self._pattern = now, decision.pattern.value

    def set_throttle(self, factor: float) -> None:
        if not math.isfinite(factor) or not 0 < factor <= 1:
            raise ValueError("rate factor must be in (0, 1]")
        self.factor = factor

    def step(self) -> None:
        now, snapshot = self.clock(), self.state.snapshot()
        changed = self._drain_changes(now)
        pattern = snapshot.decision.pattern.value
        if not changed and (self._pattern is None or now - self._last[Char.ALERT] >= 0.2 - 1e-9):
            self.emit(Char.ALERT, "alert", alert_payload(snapshot.decision, now))
            self._last[Char.ALERT], self._pattern = now, pattern
        for char, period, builder in (
            (Char.STATUS, 0.5, status_payload),
            (Char.PHYSIO, 1.0, physio_payload),
        ):
            if now - self._last[char] >= period / self.factor - 1e-9:
                self.emit(char, char.name.lower(), builder(snapshot))
                self._last[char] = now

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            self.step()
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.01)
            except TimeoutError:
                pass
