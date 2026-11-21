from __future__ import annotations

import asyncio
import sys
from enum import IntFlag
from types import SimpleNamespace

import pytest

from rtdms_pi.ble.bless_gatt import BlessGatt
from rtdms_pi.ble.gatt import GattWriteRejected
from rtdms_pi.ble.server import run_ble
from rtdms_pi.ble.uuids import GARMIN_CHAR_UUID, SERVICE_UUID, Char
from rtdms_pi.config import RuntimeConfig
from rtdms_pi.runtime import Runtime
from rtdms_pi.sources import ScriptedFrameSource


class Props(IntFlag):
    read = 1
    write = 2
    write_without_response = 4
    notify = 8


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
async def test_one_service_and_dispatch(monkeypatch, service) -> None:
    monkeypatch.setitem(
        sys.modules,
        "bless",
        SimpleNamespace(
            BlessServer=Server,
            GATTCharacteristicProperties=Props,
            GATTAttributePermissions=SimpleNamespace(readable=1, writeable=2),
        ),
    )
    port = BlessGatt()
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
