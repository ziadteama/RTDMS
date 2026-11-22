from __future__ import annotations

import asyncio
import json
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from link_spike.bench_link import (  # noqa: E402
    PROPERTIES,
    SERVICE,
    UUIDS,
    Notifications,
    check_services,
    notification_metrics,
    rejected_command,
    run_benchmark,
)

from rtdms_pi.ble.uuids import GARMIN_CHAR_UUID, SERVICE_UUID, Char  # noqa: E402


def test_contract_snapshot_and_properties() -> None:
    assert SERVICE == SERVICE_UUID
    assert UUIDS["garmin"] == GARMIN_CHAR_UUID
    for char in Char:
        assert UUIDS[char.name.lower()] == char.uuid
    chars = [SimpleNamespace(uuid=UUIDS[name], properties=list(props))
             for name, props in PROPERTIES.items()]
    services = [SimpleNamespace(uuid=SERVICE, characteristics=chars)]
    listing, errors = check_services(services)
    assert not errors
    assert len(listing[0]["characteristics"]) == 11
    chars[-1].properties = ["write"]
    assert check_services(services)[1] == ["garmin"]
    services[0].uuid = "wrong service"
    assert len(check_services(services)[1]) == 11


def test_notification_metrics_include_silent_edges() -> None:
    stats = notification_metrics([(1.0, 20), (2.0, 30), (5.0, 99)], 0, 4)
    assert stats == {
        "count": 2, "mean_hz": 0.5, "max_gap_s": 2,
        "arrival_monotonic_s": [1.0, 2.0], "payload_bytes": [20, 30],
    }
    assert notification_metrics([], 0, 30)["max_gap_s"] == 30


@pytest.mark.asyncio
async def test_result_matching_before_write_returns() -> None:
    notifications = Notifications()
    receive = notifications.callback("result")

    class Client:
        async def write_gatt_char(self, uuid: str, raw: bytes, response: bool) -> None:
            assert response
            key = json.loads(raw)["id"]
            receive(None, bytearray(b"malformed"))
            receive(None, bytearray(b'[]'))
            receive(None, bytearray(b'{"id": "unrelated", "ok": true}'))
            assert not notifications.pending[key].done()
            receive(None, bytearray(json.dumps({"id": key, "ok": True}).encode()))
            receive(None, bytearray(json.dumps({"id": key, "ok": True}).encode()))

    assert await notifications.command(Client(), "test1") >= 0
    assert not notifications.pending


@pytest.mark.asyncio
async def test_rejected_command_only_accepts_bleak_error() -> None:
    class BleakError(Exception):
        pass

    class Client:
        is_connected = True

        def __init__(self, error: Exception | None) -> None:
            self.error = error

        async def write_gatt_char(self, *args: Any, **kwargs: Any) -> None:
            if self.error:
                raise self.error

    ok, _ = await rejected_command(
        Client(BleakError("[org.bluez.Error.NotAuthorized] ATT error: 0x08")), BleakError
    )
    assert ok
    assert not (await rejected_command(Client(BleakError("ATT error: 0x0e")), BleakError))[0]
    assert not (await rejected_command(Client(None), BleakError))[0]
    dropped = Client(BleakError("NotAuthorized"))
    dropped.is_connected = False
    assert not (await rejected_command(dropped, BleakError))[0]
    with pytest.raises(TimeoutError):
        await rejected_command(Client(TimeoutError()), BleakError)


@pytest.mark.asyncio
async def test_scan_failure_is_reported_without_exception_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    class Scanner:
        @staticmethod
        async def find_device_by_filter(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("secret-token")

    fake = SimpleNamespace(BleakScanner=Scanner, BleakError=RuntimeError)
    monkeypatch.setattr("link_spike.bench_link.importlib.import_module", lambda name: fake)
    args = Namespace(name="RTDMS-Pi")
    report = await run_benchmark(args, "secret-token")
    assert not report["passed"]
    assert len(report["steps"]) == 6
    assert "secret-token" not in json.dumps(report) + capsys.readouterr().out


@pytest.mark.asyncio
async def test_cancelled_command_removes_pending() -> None:
    notifications = Notifications()

    class Client:
        async def write_gatt_char(self, *args: Any, **kwargs: Any) -> None:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await notifications.command(Client(), "cancel")
    assert not notifications.pending


@pytest.mark.asyncio
async def test_full_bench_reconnect_auth_and_result_flow(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    class BleakError(Exception):
        pass

    clients = []

    class Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.authenticated = False
            self.connected = False
            self.rejections = 0
            self.result_callback: Any = None
            self.services = [SimpleNamespace(
                uuid=SERVICE,
                characteristics=[SimpleNamespace(uuid=UUIDS[name], properties=list(props))
                                 for name, props in PROPERTIES.items()],
            )]
            clients.append(self)

        async def connect(self) -> None:
            self.connected = True

        async def disconnect(self) -> None:
            self.connected = False
            self.authenticated = False

        async def read_gatt_char(self, uuid: str) -> bytes:
            return b'{}'

        async def start_notify(self, uuid: str, callback: Any) -> None:
            if uuid == UUIDS["result"]:
                self.result_callback = callback

        async def write_gatt_char(self, uuid: str, raw: bytes, response: bool) -> None:
            assert response
            payload = json.loads(raw)
            if uuid == UUIDS["auth"]:
                assert payload == {"token": "secret-token", "contract": 1}
                self.authenticated = True
            elif not self.authenticated:
                self.rejections += 1
                raise BleakError("secret-token")
            elif uuid == UUIDS["command"]:
                self.result_callback(None, bytearray(json.dumps({
                    "id": payload["id"], "ok": True,
                }).encode()))

    class Scanner:
        @staticmethod
        async def find_device_by_filter(*args: Any, **kwargs: Any) -> object:
            assert kwargs["adapter"] == "hci0"
            return object()

    fake = SimpleNamespace(BleakScanner=Scanner, BleakClient=Client, BleakError=BleakError)
    monkeypatch.setattr("link_spike.bench_link.importlib.import_module", lambda name: fake)
    args = Namespace(name="RTDMS-Pi", samples=3, cycles=2, notify_seconds=0.001)
    report = await run_benchmark(args, "secret-token")
    steps = report["steps"]
    for name in ("discovery", "before_auth", "command_rtt", "reconnect"):
        assert steps[name]["status"] == "PASS"
    assert steps["command_rtt"]["count"] == 3
    assert steps["notifications"]["status"] == "FAIL"  # No alert stream was emitted.
    assert steps["alert_change"]["status"] == "not measurable"
    assert not report["passed"]
    assert len(clients) == 3
    assert all(client.rejections == 1 and not client.connected for client in clients)
    assert "secret-token" not in json.dumps(report) + capsys.readouterr().out
