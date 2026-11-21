"""Command dispatch with injected effects and bounded error responses."""

import logging
from collections.abc import Callable
from typing import Any

from dms_fusion import AlertPattern

from ..buzzer import PatternPlayer
from ..state import RuntimeState


def log_command(command: str, payload: dict[str, Any]) -> None:
    logging.getLogger(__name__).info("System command requested: %s (log only)", command)


def handle_command(
    payload: dict[str, Any],
    state: RuntimeState,
    player: PatternPlayer,
    on_command: Callable[[str, dict[str, Any]], None],
) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": True}
    if "id" in payload:
        result["id"] = payload["id"]
    try:
        cmd = payload["cmd"]
        if cmd == "test_alert":
            player.test_pattern(AlertPattern(payload.get("pattern", "max")))
        elif cmd == "calibrate":
            state.request_calibration()
        elif cmd in ("restart", "shutdown"):
            on_command(cmd, payload)
        else:
            result.update(ok=False, error="unknown command")
    except Exception:
        result.update(ok=False, error="command failed")
    return result
