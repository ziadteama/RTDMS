from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from conftest import Clock
from dms_fusion import AlertPattern, FusionDecision

from rtdms_pi.ble.contract import CONTRACT_VERSION, validate
from rtdms_pi.ble.gatt import GattWriteRejected
from rtdms_pi.ble.phone_service import PhoneService
from rtdms_pi.ble.uuids import GARMIN_CHAR_UUID, Char
from rtdms_pi.incidents_api import MemoryIncidentSink
from rtdms_pi.payloads import to_json_bytes

CONTRACT = Path(__file__).resolve().parents[2] / "contracts/pi-link"


def fixture(name: str) -> dict:
    return json.loads((CONTRACT / f"fixtures/{name}.json").read_text())


def write(service: PhoneService, char: Char, payload: dict) -> None:
    service.port.write(char.uuid, to_json_bytes(payload))


def unlock(service: PhoneService) -> None:
    write(service, Char.AUTH, fixture("auth"))


@pytest.mark.parametrize("char", [Char.SETTINGS, Char.COMMAND, Char.INCIDENT, Char.CLOCK])
def test_auth_gate(service: PhoneService, char: Char) -> None:
    with pytest.raises(GattWriteRejected):
        write(service, char, {})
    with pytest.raises(GattWriteRejected):
        write(service, Char.AUTH, {"token": "wrong" * 4})
    assert not service.auth.authed
    with patch(
        "rtdms_pi.ble.auth.hmac.compare_digest", wraps=__import__("hmac").compare_digest
    ) as cmp:
        unlock(service)
        cmp.assert_called_once()
    service.auth.reset()
    with pytest.raises(GattWriteRejected):
        write(service, char, {})


def test_settings(service: PhoneService) -> None:
    unlock(service)
    write(
        service, Char.SETTINGS, {"sensitivity": "high", "unknown": 3, "detectors": {"phone": False}}
    )
    full = json.loads(service.port.read(Char.SETTINGS.uuid))
    assert full["eye_closure_s"] == 2.0
    assert full["sensitivity"] == "high" and "unknown" not in full
    assert full["detectors"]["drowsiness"] and not full["detectors"]["phone"]
    write(service, Char.SETTINGS, {"eye_closure_s": 99})
    assert service.settings.read() == full
    assert service.stats.bad_writes == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"[]",
        b"null",
        b"\xff",
        b'{"phone_ms":NaN}',
        b'{"phone_ms":true}',
        b'{"phone_ms":1e999}',
    ],
)
def test_invalid_dropped(service: PhoneService, raw: bytes) -> None:
    unlock(service)
    service.port.write(Char.CLOCK.uuid, raw)
    assert service.stats.bad_writes == 1
    assert service.state.clock_offset_ms is None


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"[]",
        b"null",
        b"\xff",
        b'{"token": 123}',
        b'{"token": "short"}',
        b'{"invalid_field": "test"}',
    ],
)
def test_auth_invalid_json_or_schema_rejected(service: PhoneService, raw: bytes) -> None:
    with pytest.raises(GattWriteRejected):
        service.port.write(Char.AUTH.uuid, raw)
    assert not service.auth.authed
    assert service.stats.bad_writes >= 1


def test_auth_gate_ttl(service: PhoneService, clock: Clock) -> None:
    service.auth._clock = clock
    unlock(service)
    assert service.auth.authed
    clock.advance(100.0)
    assert service.auth.authed
    # Authenticated write touches/refreshes TTL
    write(service, Char.SETTINGS, {"sensitivity": "low"})
    clock.advance(250.0)
    assert service.auth.authed
    clock.advance(60.0)  # > 300 s since last write
    assert not service.auth.authed
    with pytest.raises(GattWriteRejected):
        write(service, Char.SETTINGS, {"sensitivity": "normal"})


def test_command_and_failures(service: PhoneService) -> None:
    unlock(service)
    write(service, Char.COMMAND, fixture("command"))
    assert json.loads(service.port.notifications[-1][1]) == fixture("command_result")
    service.player.step()
    assert ("play", 1200, 0.15) in service.player.backend.events
    write(service, Char.COMMAND, {"cmd": "calibrate"})
    assert service.state.snapshot().calibrate_requested
    calls = []
    service.on_command = lambda cmd, body: calls.append(cmd)
    write(service, Char.COMMAND, {"cmd": "restart"})
    write(service, Char.COMMAND, {"cmd": "shutdown"})
    assert calls == ["restart", "shutdown"]

    def fail(cmd: str, body: dict[str, Any]) -> None:
        raise RuntimeError("sensitive details")

    service.on_command = fail
    write(service, Char.COMMAND, {"cmd": "restart", "id": "c2"})
    assert json.loads(service.port.notifications[-1][1]) == {
        "ok": False,
        "id": "c2",
        "error": "command failed",
    }
    count = len(service.port.notifications)
    write(service, Char.COMMAND, {"cmd": "unknown"})
    assert service.stats.bad_writes == 1 and len(service.port.notifications) == count


def test_incident_clock(service: PhoneService, clock: Clock) -> None:
    unlock(service)
    write(service, Char.CLOCK, fixture("clock"))
    offset = int(clock() * 1000) - fixture("clock")["phone_ms"]
    assert service.state.clock_offset_ms == offset
    write(service, Char.INCIDENT, fixture("incident_request"))
    result = json.loads(service.port.notifications[-1][1])
    assert result == {"ok": True, "id": "2026-11-20T15-40-02-400Z"}
    assert validate("incident_response", result) == result
    write(service, Char.INCIDENT, fixture("incident_request"))
    assert json.loads(service.port.notifications[-1][1]) == result
    assert service.incidents.items[result["id"]]["pi_crash_ms"] == int(clock() * 1000)


def test_sink_thread_safety() -> None:
    sink = MemoryIncidentSink()
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: sink.report(fixture("incident_request"), 0), range(40)))
    assert len(set(ids)) == len(sink.items) == 1


def test_read_without_auth_and_budget(service: PhoneService) -> None:
    service.state.set_decision(FusionDecision(AlertPattern.MAX, ["眼" * 400] * 10))
    for char in (Char.ALERT, Char.STATUS, Char.PHYSIO, Char.HEALTH, Char.SETTINGS):
        raw = service.port.read(char.uuid)
        assert validate(char.name.lower(), json.loads(raw)) is not None
        if char != Char.SETTINGS:
            assert len(raw) <= (512 if char == Char.HEALTH else 240)
    assert CONTRACT_VERSION == 1 == fixture("health")["contract"]


@pytest.mark.parametrize("name", [p.stem for p in (CONTRACT / "fixtures").glob("*.json")])
def test_all_fixtures(name: str) -> None:
    assert validate(name, fixture(name)) == fixture(name)


@pytest.mark.parametrize(
    "char,name",
    [
        (Char.AUTH, "auth"),
        (Char.SETTINGS, "settings"),
        (Char.COMMAND, "command"),
        (Char.INCIDENT, "incident_request"),
        (Char.CLOCK, "clock"),
    ],
)
def test_write_fixtures(service: PhoneService, char: Char, name: str) -> None:
    unlock(service)
    write(service, char, fixture(name))
    assert service.stats.bad_writes == 0


@pytest.mark.asyncio
async def test_disconnect_and_subscribe(service: PhoneService) -> None:
    port = service.port
    await port.start("RTDMS-Pi")
    port.connect()
    port.subscribe(Char.ALERT.uuid)
    unlock(service)
    service.notifier.step()
    assert len(port.delivered) == 1
    port.disconnect()
    assert not service.auth.authed and port.advertising
    port.connect()
    with pytest.raises(GattWriteRejected):
        write(service, Char.CLOCK, fixture("clock"))
    assert len(port.characteristics) == 11
    assert port.characteristics[GARMIN_CHAR_UUID].props == {"write", "write_no_response"}
    await port.stop()


def test_contract_resolution_and_cache(monkeypatch: Any, tmp_path: Path) -> None:
    from rtdms_pi.ble import contract

    monkeypatch.setenv("RTDMS_CONTRACT_DIR", str(CONTRACT))
    assert contract.contract_dir() == CONTRACT
    monkeypatch.setenv("RTDMS_CONTRACT_DIR", str(tmp_path / "missing"))
    with pytest.raises(FileNotFoundError):
        contract._validators.cache_clear()
        with patch.object(Path, "is_dir", lambda p: False):
            contract.contract_dir()
    monkeypatch.setenv("RTDMS_CONTRACT_DIR", str(CONTRACT))
    contract._validators.cache_clear()
    assert validate("auth", fixture("auth")) == fixture("auth")
    with patch.object(Path, "read_text", side_effect=AssertionError("schema reloaded")):
        assert validate("clock", {"phone_ms": 1000}) == {"phone_ms": 1000}
    contract._validators.cache_clear()


@pytest.mark.asyncio
async def test_run_ble_injected_incident_sink(tmp_path: Path) -> None:
    import asyncio

    from rtdms_pi.ble.server import run_ble
    from rtdms_pi.buzzer import PatternPlayer, SilentBuzzer
    from rtdms_pi.config import RuntimeConfig
    from rtdms_pi.runtime import Runtime
    from rtdms_pi.sources import NullPhysioSource, ScriptedFrameSource
    from rtdms_pi.state import RuntimeState

    class CustomSink:
        def __init__(self) -> None:
            self.reported = False

        def report(
            self, req: dict[str, Any], clock_offset: int | None = None, **kwargs: Any
        ) -> str:
            self.reported = True
            return "custom-id"

    custom_sink = CustomSink()
    config = RuntimeConfig(state_dir=tmp_path)
    state = RuntimeState()
    player = PatternPlayer(SilentBuzzer())
    runtime = Runtime(ScriptedFrameSource([]), NullPhysioSource(), player, state)
    stop = asyncio.Event()
    stop.set()
    await run_ble(config, runtime, stop, fake=True, incidents=custom_sink)
