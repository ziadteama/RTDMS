"""Incident ingestion sink and tail-buffer completion."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

from .clip import Mp4Transcoder
from .ids import incident_id
from .ring import FrameRing
from .store import IncidentStore


class IncidentReporter(Protocol):
    def report(
        self,
        req: dict[str, Any],
        clock_offset: int | None = None,
        clock_offset_ms: int | None = None,
        **kwargs: Any,
    ) -> str: ...


class RingIncidentSink:
    def __init__(
        self,
        ring: FrameRing,
        store: IncidentStore,
        transcoder: Mp4Transcoder | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        scheduler: Callable[[float, Callable[[], None]], Any] | None = None,
    ) -> None:
        self.ring = ring
        self.store = store
        self.transcoder = transcoder
        # Pi monotonic: the phone clock offset (pi_mono_ms - phone_ms) maps t_crash onto it.
        self.clock, self.wall = clock, wall
        self.scheduler = scheduler or self._default_schedule
        self._pending: dict[str, str] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _default_schedule(delay_s: float, callback: Callable[[], None]) -> threading.Timer:
        timer = threading.Timer(max(0.0, delay_s), callback)
        timer.daemon = True
        timer.start()
        return timer

    def _resolve_offset(
        self,
        clock_offset_ms: int | None,
        kwargs: dict[str, Any],
    ) -> int | None:
        if clock_offset_ms is not None:
            return clock_offset_ms
        val = kwargs.get("clock_offset")
        return int(val) if val is not None else None

    def _resolve_crash_times(
        self, t_crash_raw: Any, offset: int | None, now_s: float
    ) -> tuple[int, int, bool]:
        now_ms = int(now_s * 1000)
        if offset is not None and t_crash_raw is not None:
            t_crash = int(t_crash_raw)
            return (t_crash, t_crash + offset, True)
        if t_crash_raw is not None:
            t_crash = int(t_crash_raw)
            return (t_crash, now_ms, False)
        return (now_ms, now_ms, False)

    def _schedule_snapshot(
        self,
        inc_id: str,
        meta: dict[str, Any],
        t_start: float,
        t_end: float,
        delay: float,
    ) -> None:
        def _finish_snapshot() -> None:
            try:
                entries = self.ring.window(t_start, t_end)
                inc_dir = self.store.save_incident(inc_id, meta, entries)
                if self.transcoder is not None:
                    self.transcoder.enqueue(inc_dir)
            finally:
                client_id = meta.get("client_id")
                if isinstance(client_id, str) and client_id:
                    with self._lock:
                        self._pending.pop(client_id, None)

        self.scheduler(delay, _finish_snapshot)

    def report(
        self,
        req: dict[str, Any],
        clock_offset: int | None = None,
        clock_offset_ms: int | None = None,
        **kwargs: Any,
    ) -> str:
        actual_offset = clock_offset if clock_offset is not None else clock_offset_ms
        offset = self._resolve_offset(actual_offset, kwargs)
        client_id = req.get("client_id")
        now_s = self.clock()
        t_crash, pi_ms, synced = self._resolve_crash_times(req.get("t_crash"), offset, now_s)
        inc_id = incident_id(t_crash)

        if isinstance(client_id, str) and client_id:
            with self._lock:
                if client_id in self._pending:
                    return self._pending[client_id]
                persisted_id = self.store.find_by_client_id(client_id)
                if persisted_id:
                    return persisted_id
                self._pending[client_id] = inc_id

        pi_s = pi_ms / 1000.0
        t_start, t_end = pi_s - 20.0, pi_s + 5.0
        delay = max(0.0, t_end - now_s)
        meta = {
            "id": inc_id,
            "client_id": client_id,
            "t_crash": t_crash,
            "g_peak": float(req.get("g_peak", 0.0)),
            "lat": req.get("lat"),
            "lon": req.get("lon"),
            "clock_synced": synced,
            "created": self.wall(),
            "duration_s": 25.0,
        }
        self._schedule_snapshot(inc_id, meta, t_start, t_end, delay)
        return inc_id
