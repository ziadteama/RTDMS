"""Incident identifier generation."""

from __future__ import annotations

from datetime import UTC, datetime


def incident_id(t_crash_ms: int | float) -> str:
    """Generate canonical incident identifier formatted as UTC %Y-%m-%dT%H-%M-%S-{ms:03d}Z."""
    ms_int = int(t_crash_ms)
    seconds, ms = divmod(ms_int, 1000)
    stamp = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{stamp}-{ms:03d}Z"
