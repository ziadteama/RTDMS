"""Single-service bless 0.2.x adapter. Not verified on hardware."""

import asyncio
import importlib
import logging
from collections.abc import Callable
from typing import Any

from .gatt import Characteristic, GattWriteRejected
from .uuids import SERVICE_UUID


class BlessGatt:
    def __init__(self) -> None:
        self.characteristics: dict[str, Characteristic] = {}
        self.server: Any = None  # untyped optional hardware boundary
        self._disconnect: Callable[[], None] = lambda: None

    def add_characteristic(
        self,
        uuid: str,
        props: frozenset[str],
        on_read: Callable[[], bytes] | None,
        on_write: Callable[[bytes], None] | None,
    ) -> None:
        self.characteristics[uuid.lower()] = Characteristic(props, on_read, on_write)

    def set_disconnect_handler(self, callback: Callable[[], None]) -> None:
        self._disconnect = callback

    def on_disconnect(self) -> None:
        # bless 0.2.x does not invoke this automatically. Never stop advertising here.
        self._disconnect()

    def _read(self, characteristic: Any, **kwargs: Any) -> bytearray:
        callback = self.characteristics[str(characteristic.uuid).lower()].on_read
        return bytearray(callback() if callback else b"")

    def _write(self, characteristic: Any, value: Any, **kwargs: Any) -> None:
        callback = self.characteristics[str(characteristic.uuid).lower()].on_write
        if callback:
            try:
                callback(bytes(value))
            except GattWriteRejected:
                logging.getLogger(__name__).warning("BLE write rejected: authentication required")
                raise  # best effort: ATT mapping depends on the bless backend

    async def start(self, name: str) -> None:
        bless = importlib.import_module("bless")
        self.server = bless.BlessServer(name=name, loop=asyncio.get_running_loop())
        self.server.read_request_func, self.server.write_request_func = self._read, self._write
        await self.server.add_new_service(SERVICE_UUID)
        props, perms = bless.GATTCharacteristicProperties, bless.GATTAttributePermissions
        for uuid, char in self.characteristics.items():
            flags, permissions = props(0), perms(0)  # real bless enums are Flag, not int
            for prop in char.props:
                flags |= getattr(
                    props, "write_without_response" if prop == "write_no_response" else prop
                )
            if "read" in char.props:
                permissions |= perms.readable
            if char.props & {"write", "write_no_response"}:
                permissions |= perms.writeable
            await self.server.add_new_characteristic(SERVICE_UUID, uuid, flags, None, permissions)
        await self.server.start()

    def notify(self, uuid: str, value: bytes) -> None:
        if self.server is not None:
            self.server.get_characteristic(uuid).value = bytearray(value)
            self.server.update_value(SERVICE_UUID, uuid)

    async def stop(self) -> None:
        server, self.server = self.server, None
        if server is not None:
            try:
                await server.stop()
            except IndexError:  # bless pops its advertisement list; empty if start() never got there
                pass
