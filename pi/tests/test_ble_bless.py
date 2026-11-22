from __future__ import annotations

import asyncio
import sys
from enum import Flag, auto
from types import SimpleNamespace

import pytest

from rtdms_pi import pairing
from rtdms_pi.ble.bless_gatt import BlessGatt, connected_flag
from rtdms_pi.ble.gatt import GattWriteRejected
from rtdms_pi.ble.server import run_ble
from rtdms_pi.ble.uuids import GARMIN_CHAR_UUID, SERVICE_UUID, Char
from rtdms_pi.config import RuntimeConfig
from rtdms_pi.runtime import Runtime
from rtdms_pi.sources import ScriptedFrameSource


class Props(Flag):  # real bless enums are Flag: `0 | Props.x` raises TypeError
    read = auto()
    write = auto()
    write_without_response = auto()
    notify = auto()


class Perms(Flag):
    readable = auto()
    writeable = auto()


class DBusError(Exception):
    def __init__(self, name, text):
        super().__init__(text)
        self.type = name


class Bus:
    def __init__(self):
        self.handlers = []
        self.calls = []
        self.disconnects = 0
        self.connected = False

    async def connect(self):
        self.connected = True
        return self

    def add_message_handler(self, handler):
        self.handlers.append(handler)

    async def call(self, message):
        self.calls.append(message)
        return SimpleNamespace(message_type="return")

    def disconnect(self):
        self.disconnects += 1

    def fire(self, body, **kwargs):
        fields = dict(
            message_type="signal",
            interface="org.freedesktop.DBus.Properties",
            member="PropertiesChanged",
            path="/org/bluez/hci0/dev_01",
            body=body,
        )
        fields.update(kwargs)
        for handler in self.handlers:
            handler(SimpleNamespace(**fields))


@pytest.fixture
def dbus(monkeypatch):
    module = SimpleNamespace(
        DBusError=DBusError,
        Message=SimpleNamespace,
        MessageType=SimpleNamespace(SIGNAL="signal", ERROR="error"),
    )
    monkeypatch.setitem(sys.modules, "dbus_fast", module)
    return module


@pytest.fixture
def bless(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "bless",
        SimpleNamespace(
            BlessServer=Server,
            GATTCharacteristicProperties=Props,
            GATTAttributePermissions=Perms,
        ),
    )


class Server:
    def __init__(self, **kwargs):
        self.services = []
        self.chars = {}
        self.updates = []
        self.stops = 0
        self.started = False

    async def add_new_service(self, uuid):
        self.services.append(uuid)

    async def add_new_characteristic(self, service, uuid, props, value, permissions):
        assert service == SERVICE_UUID
        self.chars[uuid] = SimpleNamespace(
            uuid=uuid, value=value, props=props, permissions=permissions
        )

    async def start(self):
        self.started = True

    async def stop(self):
        self.stops += 1

    def get_characteristic(self, uuid):
        return self.chars[uuid]

    def update_value(self, service, uuid):
        self.updates.append((service, uuid))


@pytest.mark.asyncio
async def test_one_service_and_dispatch(monkeypatch, service, bless, dbus) -> None:
    port = BlessGatt(bus_factory=Bus)
    for uuid, char in service.port.characteristics.items():
        port.add_characteristic(uuid, char.props, char.on_read, char.on_write)
    port.set_disconnect_handler(service.on_disconnect)
    await port.start("test")
    server = port.server
    assert server.services == [SERVICE_UUID]
    assert len(server.chars) == 11  # ten phone entries plus Garmin: contract authority
    assert server.chars[GARMIN_CHAR_UUID].props == Props.write | Props.write_without_response
    assert server.chars[Char.SETTINGS.uuid].props == Props.read | Props.write
    assert server.chars[Char.RESULT.uuid].props == Props.notify
    assert server.read_request_func(server.chars[Char.HEALTH.uuid])
    monkeypatch.setitem(sys.modules, "dbus_fast", None)
    with pytest.raises(GattWriteRejected):
        server.write_request_func(server.chars[Char.CLOCK.uuid], b'{"phone_ms":1}')
    port.notify(Char.ALERT.uuid, b"value")
    assert server.chars[Char.ALERT.uuid].value == b"value"
    assert server.updates == [(SERVICE_UUID, Char.ALERT.uuid)]
    service.auth.authed = True
    port.on_disconnect()
    assert not service.auth.authed and server.started and server.stops == 0
    await port.stop()
    assert server.stops == 1


@pytest.mark.asyncio
async def test_server_lifecycle(tmp_path, service) -> None:
    runtime = Runtime(ScriptedFrameSource([]), service.garmin, service.player, service.state)
    config = RuntimeConfig(state_dir=tmp_path, ble_name="Custom-Pi")
    stop = asyncio.Event()
    task = asyncio.create_task(run_ble(config, runtime, stop, port=service.port))
    await asyncio.sleep(0)
    assert service.port.advertising and service.port.name == "Custom-Pi"
    stop.set()
    await task
    assert not service.port.advertising
    assert len((tmp_path / "token").read_text().strip()) >= 16
    assert (tmp_path / "token").stat().st_mode & 0o777 == 0o600


def test_cli_switches() -> None:
    assert RuntimeConfig.from_args(["--ble"]).ble is True
    assert RuntimeConfig.from_args(["--no-ble"]).ble is False
    assert RuntimeConfig.from_args(["--fake-ble"]).fake_ble


def test_write_not_authorized(service, dbus, caplog) -> None:
    port = BlessGatt()
    char = service.port.characteristics[Char.CLOCK.uuid]
    port.add_characteristic(Char.CLOCK.uuid, char.props, char.on_read, char.on_write)
    payload = b'{"phone_ms":1,"token":"private-test-token"}'
    with pytest.raises(DBusError) as caught:
        port._write(SimpleNamespace(uuid=Char.CLOCK.uuid), payload)
    assert caught.value.type == "org.bluez.Error.NotAuthorized"
    assert str(caught.value) == "authentication required"
    assert "BLE write rejected: authentication required" in caplog.text
    assert "private-test-token" not in caplog.text
    assert "phone_ms" not in caplog.text


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (["org.bluez.Device1", {"Connected": SimpleNamespace(value=False)}, []], False),
        (["org.bluez.Device1", {"Connected": SimpleNamespace(value=True)}, []], True),
        (["org.bluez.Adapter1", {"Connected": SimpleNamespace(value=False)}, []], None),
        (["org.bluez.Device1", {"Paired": SimpleNamespace(value=False)}, []], None),
        (["org.bluez.Device1", {}, ["Connected"]], None),
        (["org.bluez.Device1", {"Connected": SimpleNamespace(value=0)}, []], None),
        ([], None),
        (None, None),
    ],
)
def test_connected_flag(body, expected) -> None:
    assert connected_flag(body) is expected


@pytest.mark.asyncio
async def test_bluez_disconnect(bless, dbus, service) -> None:
    bus = Bus()
    port = BlessGatt(bus_factory=lambda: bus)
    calls = []

    def disconnected():
        calls.append(True)
        service.on_disconnect()

    port.set_disconnect_handler(disconnected)
    await port.start("test")
    server = port.server
    assert bus.connected and len(bus.handlers) == 1
    assert bus.calls[0].member == "AddMatch"
    assert bus.calls[0].body == [
        "type='signal',interface='org.freedesktop.DBus.Properties',"
        "member='PropertiesChanged',path_namespace='/org/bluez'"
    ]
    service.auth.authed = True
    for interface, changed in [
        ("org.bluez.Device1", {"Connected": SimpleNamespace(value=True)}),
        ("org.bluez.Adapter1", {"Connected": SimpleNamespace(value=False)}),
        ("org.bluez.Device1", {"Paired": SimpleNamespace(value=False)}),
    ]:
        bus.fire([interface, changed, []])
    body = ["org.bluez.Device1", {"Connected": SimpleNamespace(value=False)}, []]
    for overrides in [
        {"message_type": "return"},
        {"interface": "other"},
        {"member": "other"},
        {"path": "/other/device"},
    ]:
        bus.fire(body, **overrides)
    assert calls == [] and service.auth.authed
    bus.fire(body)
    assert calls == [True] and not service.auth.authed
    assert server.started and server.stops == 0
    await port.stop()
    await port.stop()
    assert bus.disconnects == 1 and server.stops == 1


def test_pairing_and_advertising_names(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("RTDMS_BLE_NAME", raising=False)
    monkeypatch.setattr(pairing, "render_qr_ascii", lambda text: "")
    assert RuntimeConfig().ble_name == "RTDMS-Pi"
    assert RuntimeConfig.from_args([]).ble_name == "RTDMS-Pi"
    assert RuntimeConfig.from_args(["--ble-name", "X"]).ble_name == "X"
    assert (
        pairing.main(
            [
                "--state-dir",
                str(tmp_path),
                "--psk-file",
                str(tmp_path / "wifi_psk"),
                "--force",
            ]
        )
        == 0
    )
    assert ";B:RTDMS-Pi;" in capsys.readouterr().out
