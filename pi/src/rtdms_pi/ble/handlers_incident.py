"""Incident dispatch independent of BLE."""

from typing import Any

from ..incidents_api import IncidentSink


def handle_incident(
    payload: dict[str, Any], sink: IncidentSink, clock_offset: int | None
) -> dict[str, Any]:
    try:
        return {"ok": True, "id": sink.report(payload, clock_offset)}
    except Exception:
        return {"ok": False, "error": "incident failed"}
