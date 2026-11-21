"""In-process central and GATT table; no Bluetooth dependencies."""

import time
from collections.abc import Callable

from .gatt import Characteristic


class FakeGatt:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.characteristics: dict[str, Characteristic] = {}
        self.notifications: list[tuple[str, bytes]] = []
        self.delivered: list[tuple[float, str, bytes]] = []
        self.subscriptions: set[str] = set()
        self.connected = False
        self.advertising = False
        self.name = ""
        self._disconnect: Callable[[], None] = lambda: None

    def add_characteristic(
        self,
        uuid: str,
        props: frozenset[str],
        on_read: Callable[[], bytes] | None,
        on_write: Callable[[bytes], None] | None,
    ) -> None:
        self.characteristics[uuid] = Characteristic(props, on_read, on_write)

    def set_disconnect_handler(self, callback: Callable[[], None]) -> None:
        self._disconnect = callback

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False
        self.subscriptions.clear()
        self._disconnect()

    def subscribe(self, uuid: str) -> None:
        if "notify" not in self.characteristics[uuid].props:
            raise ValueError("not notifiable")
        self.subscriptions.add(uuid)

    def write(self, uuid: str, value: bytes) -> None:
        callback = self.characteristics[uuid].on_write
        if callback is None:
            raise ValueError("not writable")
        callback(value)

    def read(self, uuid: str) -> bytes:
        callback = self.characteristics[uuid].on_read
        if callback is None:
            raise ValueError("not readable")
        return callback()

    def notify(self, uuid: str, value: bytes) -> None:
        self.notifications.append((uuid, value))
        if self.connected and uuid in self.subscriptions:
            self.delivered.append((self.clock(), uuid, value))

    async def start(self, name: str) -> None:
        self.name, self.advertising = name, True

    async def stop(self) -> None:
        self.advertising = False
