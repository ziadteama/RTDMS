"""BLE lifecycle shared by the runtime and simulated deployments."""

import asyncio
import signal
import time
from collections.abc import Callable
from typing import Any

from ..config import RuntimeConfig
from ..health import HealthProbe
from ..incidents_api import IncidentSink, MemoryIncidentSink
from ..pairing import load_or_create_token
from ..runtime import Runtime
from ..settings import SettingsStore
from ..sources import GarminPhysioSource
from .auth import AuthGate
from .bless_gatt import BlessGatt
from .fake_gatt import FakeGatt
from .gatt import GattPort
from .phone_service import PhoneService


def health_reader(
    runtime: Runtime,
    config: RuntimeConfig,
    settings: SettingsStore | None = None,
) -> Callable[[], dict[str, Any]]:
    probe = HealthProbe(
        state=runtime.state,
        settings_provider=settings.read if settings else runtime.settings_provider,
        physio_source=runtime.physio_source,
        config=config,
        state_dir=config.state_dir,
    )
    return probe


async def run_ble(
    config: RuntimeConfig,
    runtime: Runtime,
    stop: asyncio.Event | None = None,
    *,
    fake: bool = False,
    port: GattPort | None = None,
    incidents: IncidentSink | None = None,
    settings: SettingsStore | None = None,
) -> None:
    port = port if port is not None else FakeGatt() if fake else BlessGatt()
    stop = stop if stop is not None else asyncio.Event()
    garmin = runtime.physio_source
    incident_sink = incidents if incidents is not None else MemoryIncidentSink()
    settings_store = (
        settings
        if settings is not None
        else SettingsStore(config.state_dir / "settings.json")
    )
    service = PhoneService(
        port,
        runtime.state,
        runtime.player,
        settings_store,
        incident_sink,
        time.time,
        AuthGate(load_or_create_token(config.state_dir / "token")),
        health_reader(runtime, config, settings_store),
        garmin=garmin if isinstance(garmin, GarminPhysioSource) else None,
        start_calibration=runtime.frame_source.start_calibration,
        apply_phone_calibration=runtime.frame_source.apply_phone_calibration,
    )
    try:
        await port.start(config.ble_name)
        await service.run(stop)
    finally:
        await port.stop()
        service.on_disconnect()
        service.notifier.close()


async def run_runtime_ble(
    config: RuntimeConfig,
    runtime: Runtime,
    *,
    incidents: IncidentSink | None = None,
    settings: SettingsStore | None = None,
) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    for sig in previous:
        loop.add_signal_handler(sig, stop.set)
    try:
        runtime.start()
        await run_ble(
            config,
            runtime,
            stop,
            fake=config.fake_ble,
            incidents=incidents,
            settings=settings,
        )
    finally:
        runtime.stop()
        for sig, handler in previous.items():
            loop.remove_signal_handler(sig)
            signal.signal(sig, handler)
