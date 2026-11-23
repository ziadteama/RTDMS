"""Event-driven, send-on-change telemetry schedule, testable by step()."""

import asyncio
import logging
import math
from collections.abc import Callable, Mapping
from queue import Empty, SimpleQueue
from typing import Any

from ..payloads import alert_payload, physio_payload, status_payload, to_json_bytes
from ..state import DecisionSnapshot, RuntimeState
from ..watch_alert import WatchAlert
from .uuids import Char

EPS = 1e-9
ALERT_KEEPALIVE_S = 1.0
STATUS_KEEPALIVE_S = 5.0
_STATUS_DP = {"perclos": 2, "openness": 2, "phone_p": 2, "blink_rate": 1, "temp_c": 1}


def _is_num(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _status_key(payload: dict[str, object]) -> bytes:
    q: dict[str, Any] = dict(payload)
    for key, value in payload.items():
        if not _is_num(value):
            continue
        if key == "fps":
            q[key] = round(value)  # type: ignore[call-overload]
        elif key == "closure_ms":
            q[key] = round(value / 100) * 100  # type: ignore[operator]
        elif key in _STATUS_DP:
            q[key] = round(value, _STATUS_DP[key])  # type: ignore[call-overload]
    return to_json_bytes(q)


def _alert_key(payload: dict[str, object]) -> bytes:
    return to_json_bytes({k: v for k, v in payload.items() if k != "t"})


def _physio_key(payload: dict[str, object]) -> bytes:
    if payload.get("watch_connected") is True:
        return to_json_bytes(payload)
    return _alert_key(payload)


WATCH_KEEPALIVE_S = 5.0

class Notifier:
    def __init__(
        self,
        state: RuntimeState,
        clock: Callable[[], float],
        emit: Callable[[Char, str, dict[str, object]], None],
        settings_provider: Callable[[], Mapping[str, object]] | None = None,
        watch: WatchAlert | None = None,
        emit_raw: Callable[[Char, bytes], None] | None = None,
    ) -> None:
        self.state, self.clock, self.emit = state, clock, emit
        self.watch, self.emit_raw = watch, emit_raw
        self._watch_at = float("-inf")
        self.settings_provider = settings_provider
        self.factor = 1.0
        self.wakeups = 0
        self._sent_at = {char: float("-inf") for char in (Char.ALERT, Char.STATUS, Char.PHYSIO)}
        self._key: dict[Char, bytes] = {}
        self._checked_at = float("-inf")
        self._changes: SimpleQueue[DecisionSnapshot] = SimpleQueue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None
        self.state.subscribe_decisions(self._on_change)

    def close(self) -> None:
        self.state.unsubscribe_decisions(self._on_change)

    def _on_change(self, decision: DecisionSnapshot) -> None:
        self._changes.put(decision)
        loop, wake = self._loop, self._wake
        if loop is not None and wake is not None:
            try:
                loop.call_soon_threadsafe(wake.set)
            except RuntimeError:
                pass

    def _send(
        self, char: Char, schema: str, payload: dict[str, object], key: bytes, now: float
    ) -> None:
        try:
            self.emit(char, schema, payload)
        except Exception:  # one bad payload or a dead link must not end the telemetry loop
            logging.getLogger(__name__).exception("BLE notify failed: %s", char.name)
        self._sent_at[char], self._key[char] = now, key

    def _send_alert(self, payload: dict[str, object], now: float, *, keepalive: bool) -> bool:
        key = _alert_key(payload)
        if not keepalive and self._key.get(Char.ALERT) == key:
            return False
        self._send(Char.ALERT, "alert", payload, key, now)
        return True

    def _drain_changes(self, now: float) -> bool:
        emitted = False
        while True:
            try:
                decision = self._changes.get_nowait()
            except Empty:
                return emitted
            emitted |= self._send_alert(
                alert_payload(decision, now, self.state.phone_clock), now, keepalive=False
            )
            if self.watch is not None:
                self._send_watch(self.watch.change(decision.pattern), now)

    def _send_watch(self, value: bytes, now: float) -> None:
        """Garmin watch alert: 2 raw bytes on every change, then a 5 s keep-alive."""
        if self.watch is None or self.emit_raw is None:
            return
        try:
            self.emit_raw(Char.WATCH_ALERT, value)
            self.watch.sent(value, now)
        except Exception:
            logging.getLogger(__name__).exception("BLE notify failed: WATCH_ALERT")
        self._watch_at = now

    def set_throttle(self, factor: float) -> None:
        if not math.isfinite(factor) or not 0 < factor <= 1:
            raise ValueError("rate factor must be in (0, 1]")
        self.factor = factor

    def _check_status(self, snapshot: Any, now: float) -> None:
        st = self.settings_provider() if self.settings_provider else None
        payload = status_payload(snapshot, st)
        key = _status_key(payload)
        stale = now - self._sent_at[Char.STATUS] >= STATUS_KEEPALIVE_S / self.factor - EPS
        if stale or key != self._key.get(Char.STATUS):
            self._send(Char.STATUS, "status", payload, key, now)

    def _check_physio(self, snapshot: Any, now: float) -> None:
        payload = physio_payload(snapshot, self.state.phone_clock)
        key = _physio_key(payload)
        stale = now - self._sent_at[Char.PHYSIO] >= STATUS_KEEPALIVE_S / self.factor - EPS
        # keep-alive: a late subscriber needs a state
        if stale or key != self._key.get(Char.PHYSIO):
            self._send(Char.PHYSIO, "physio", payload, key, now)

    def step(self) -> None:
        now, snapshot = self.clock(), self.state.snapshot()
        changed = self._drain_changes(now)
        if not changed and now - self._sent_at[Char.ALERT] >= ALERT_KEEPALIVE_S - EPS:
            self._send_alert(
                alert_payload(snapshot.decision, now, self.state.phone_clock), now, keepalive=True
            )
        if self.watch is not None and now - self._watch_at >= WATCH_KEEPALIVE_S - EPS:
            self._send_watch(self.watch.read(), now)
        if changed or now - self._checked_at >= 1.0 / self.factor - EPS:
            self._checked_at = now
            self._check_status(snapshot, now)
            self._check_physio(snapshot, now)

    def _next_due(self) -> float:
        alert_due = self._sent_at[Char.ALERT] + ALERT_KEEPALIVE_S
        watch_due = self._watch_at + WATCH_KEEPALIVE_S if self.watch is not None else math.inf
        return min(alert_due, self._checked_at + 1.0 / self.factor, watch_due)

    async def run(self, stop: asyncio.Event) -> None:
        self._loop, wake = asyncio.get_running_loop(), asyncio.Event()
        self._wake = wake
        watcher = asyncio.create_task(stop.wait())
        watcher.add_done_callback(lambda _: wake.set())
        try:
            while not stop.is_set():
                self.wakeups += 1
                self.step()
                timeout = max(0.001, self._next_due() - self.clock())
                try:
                    await asyncio.wait_for(wake.wait(), timeout)
                except TimeoutError:
                    pass
                wake.clear()
        finally:
            watcher.cancel()
            self._loop = self._wake = None
