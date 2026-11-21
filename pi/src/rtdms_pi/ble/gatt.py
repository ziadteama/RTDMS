"""BLE-independent transport interface."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class GattWriteRejected(Exception):
    """ATT insufficient authentication (best effort with bless)."""


@dataclass
class Characteristic:
    props: frozenset[str]
    on_read: Callable[[], bytes] | None
    on_write: Callable[[bytes], None] | None


class GattPort(Protocol):
    def add_characteristic(
        self,
        uuid: str,
        props: frozenset[str],
        on_read: Callable[[], bytes] | None,
        on_write: Callable[[bytes], None] | None,
    ) -> None: ...
    def notify(self, uuid: str, value: bytes) -> None: ...
    def set_disconnect_handler(self, callback: Callable[[], None]) -> None: ...
    async def start(self, name: str) -> None: ...
    async def stop(self) -> None: ...
