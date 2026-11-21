"""Incident storage strategy; P3 keeps metadata only, without clips."""

from threading import Lock
from typing import Any, Protocol

from .incidents.ids import incident_id as format_incident_id


class IncidentSink(Protocol):
    def report(
        self,
        req: dict[str, Any],
        clock_offset: int | None = None,
        clock_offset_ms: int | None = None,
        **kwargs: Any,
    ) -> str: ...


class MemoryIncidentSink:
    def __init__(self) -> None:
        self._lock = Lock()
        self._clients: dict[str, str] = {}
        self.items: dict[str, dict[str, Any]] = {}

    def report(
        self,
        req: dict[str, Any],
        clock_offset: int | None = None,
        clock_offset_ms: int | None = None,
        **kwargs: Any,
    ) -> str:
        offset = clock_offset if clock_offset is not None else clock_offset_ms
        with self._lock:
            client = req.get("client_id")
            if client is not None and client in self._clients:
                return self._clients[client]
            inc_id = format_incident_id(req["t_crash"])
            pi_crash_ms = (
                req["t_crash"] + offset if offset is not None else req["t_crash"]
            )
            self.items[inc_id] = dict(
                req, id=inc_id, clip_ready=False, pi_crash_ms=pi_crash_ms
            )
            if client is not None:
                self._clients[client] = inc_id
            return inc_id
