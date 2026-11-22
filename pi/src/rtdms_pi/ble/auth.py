"""Pairing gate; bless 0.2.x requires an explicit disconnect/reset hook or TTL expiry."""

from __future__ import annotations

import hmac
import time
from collections.abc import Callable
from typing import Any

from .contract import validate


class AuthGate:
    def __init__(
        self,
        token: str,
        ttl_s: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
        open_mode: bool = False,
    ) -> None:
        # DEV ONLY: open mode treats every connection as authenticated (no token needed).
        self.open_mode = open_mode
        self._token = token.encode("utf-8")
        self.ttl_s = float(ttl_s)
        self._clock = clock
        self._last_auth_time: float | None = None

    @property
    def authed(self) -> bool:
        if self.open_mode:
            return True
        if self._last_auth_time is None:
            return False
        if (self._clock() - self._last_auth_time) > self.ttl_s:
            self._last_auth_time = None
            return False
        return True

    @authed.setter
    def authed(self, value: bool) -> None:
        if value:
            self._last_auth_time = self._clock()
        else:
            self._last_auth_time = None

    def touch(self) -> None:
        """Refresh TTL on authenticated write."""
        if self.authed:
            self._last_auth_time = self._clock()

    def accept(self, payload: dict[str, Any]) -> bool:
        clean = validate("auth", payload)
        if clean is not None and hmac.compare_digest(
            clean["token"].encode("utf-8"), self._token
        ):
            self._last_auth_time = self._clock()
            return True
        return False

    def reset(self) -> None:
        self._last_auth_time = None
