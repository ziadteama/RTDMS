"""Clock alignment and authentication effects."""

from typing import Any

from ..state import RuntimeState
from .auth import AuthGate
from .gatt import GattWriteRejected


def handle_clock(payload: dict[str, Any], state: RuntimeState, pi_time_ms: int) -> None:
    state.set_clock_offset(pi_time_ms - payload["phone_ms"])


def handle_auth(payload: dict[str, Any], auth: AuthGate) -> None:
    if not auth.accept(payload):
        raise GattWriteRejected("insufficient authentication")
