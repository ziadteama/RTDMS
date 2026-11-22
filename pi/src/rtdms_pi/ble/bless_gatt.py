"""Single-service bless 0.2.x adapter.

Any BlueZ peer disconnect resets auth, including a Garmin watch using this service:
bless does not expose the phone's Device1 path. The phone re-authenticates on its
next rejected write.
"""

import asyncio
import importlib
import logging
from collections.abc import Callable
from typing import Any

from .gatt import Characteristic, GattWriteRejected
from .uuids import SERVICE_UUID


def connected_flag(message: Any) -> bool | None:
    """Parse a PropertiesChanged signal body without importing D-Bus."""
    if not isinstance(message, (list, tuple)) or len(message) != 3:
        return None
    interface, changed, _invalidated = message
    if interface != "org.bluez.Device1" or not isinstance(changed, dict):
        return None
    value = getattr(changed.get("Connected"), "value", None)
    return value if isinstance(value, bool) else None


def _system_bus() -> Any:
    dbus = importlib.import_module("dbus_fast")
    aio = importlib.import_module("dbus_fast.aio")
    return aio.MessageBus(bus_type=dbus.BusType.SYSTEM)


class BlessGatt:
    def __init__(self, bus_factory: Callable[[], Any] = _system_bus) -> None:
        self.characteristics: dict[str, Characteristic] = {}
        self.server: Any = None  # untyped optional hardware boundary
        self._disconnect: Callable[[], None] = lambda: None
        self._bus_factory = bus_factory
        self._bus: Any = None

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
            except GattWriteRejected as exc:
                logging.getLogger(__name__).warning("BLE write rejected: authentication required")
                try:
                    dbus = importlib.import_module("dbus_fast")
                except ImportError:
                    raise exc from None
                raise dbus.DBusError(
                    "org.bluez.Error.NotAuthorized", "authentication required"
                ) from None

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
        try:
            dbus = importlib.import_module("dbus_fast")
            self._bus = self._bus_factory()
            await self._bus.connect()

            def on_message(message: Any) -> None:
                if (
                    message.message_type == dbus.MessageType.SIGNAL
                    and message.interface == "org.freedesktop.DBus.Properties"
                    and message.member == "PropertiesChanged"
                    and (message.path or "").startswith("/org/bluez/")
                    and connected_flag(message.body) is False
                ):
                    self.on_disconnect()

            self._bus.add_message_handler(on_message)
            reply = await self._bus.call(
                dbus.Message(
                    destination="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    interface="org.freedesktop.DBus",
                    member="AddMatch",
                    signature="s",
                    body=[
                        "type='signal',interface='org.freedesktop.DBus.Properties',"
                        "member='PropertiesChanged',path_namespace='/org/bluez'"
                    ],
                )
            )
            if reply.message_type == dbus.MessageType.ERROR:
                raise RuntimeError("Could not subscribe to BlueZ disconnect signals")
        except BaseException:
            await self.stop()
            raise

    def notify(self, uuid: str, value: bytes) -> None:
        if self.server is not None:
            self.server.get_characteristic(uuid).value = bytearray(value)
            self.server.update_value(SERVICE_UUID, uuid)

    async def stop(self) -> None:
        bus, self._bus = self._bus, None
        if bus is not None:
            bus.disconnect()
        server, self.server = self.server, None
        if server is not None:
            try:
                await server.stop()
            except IndexError:  # bless pops an empty advertisement list if start() failed
                pass
