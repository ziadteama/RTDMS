"""BLE lifecycle shared by the runtime and simulated deployments."""

import asyncio
import signal
import time
from collections.abc import Callable
from typing import Any

from ..config import RuntimeConfig
from ..incidents_api import IncidentSink, MemoryIncidentSink
from ..pairing import load_or_create_token
from ..payloads import health_payload
from ..runtime import Runtime
from ..settings import SettingsStore
from ..sources import GarminPhysioSource
from .auth import AuthGate
from .bless_gatt import BlessGatt
from .fake_gatt import FakeGatt
from .gatt import GattPort
from .phone_service import PhoneService


def health_reader(runtime: Runtime, config: RuntimeConfig) -> Callable[[], dict[str, Any]]:
    started, cpu_started = time.monotonic(), time.process_time()

    def read() -> dict[str, Any]:
        s, elapsed = runtime.state.snapshot(), time.monotonic() - started
        return health_payload(
            cpu_pct=100 * (time.process_time() - cpu_started) / max(elapsed, 1e-9),
            fps=s.fps,
            uptime_s=elapsed,
            camera=s.camera_ok,
            temp_c=s.temp_c,
            models={
                "fusion": "running",
                "face": "off" if config.no_camera else "running" if s.face else "error",
                "distraction": "off" if config.no_camera else "running" if s.phone else "error",
                "physiology": "running" if s.physio else "error" if config.physiology else "off",
            },
        )

    return read


async def run_ble(
    config: RuntimeConfig,
    runtime: Runtime,
    stop: asyncio.Event | None = None,
    *,
    fake: bool = False,
    port: GattPort | None = None,
    incidents: IncidentSink | None = None,
) -> None:
    port = port if port is not None else FakeGatt() if fake else BlessGatt()
    stop = stop if stop is not None else asyncio.Event()
    garmin = runtime.physio_source
    incident_sink = incidents if incidents is not None else MemoryIncidentSink()
    service = PhoneService(
        port,
        runtime.state,
        runtime.player,
        SettingsStore(),
        incident_sink,
        time.time,
        AuthGate(load_or_create_token(config.state_dir / "token")),
        health_reader(runtime, config),
        garmin=garmin if isinstance(garmin, GarminPhysioSource) else None,
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
) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    for sig in previous:
        loop.add_signal_handler(sig, stop.set)
    try:
        runtime.start()
        await run_ble(config, runtime, stop, fake=config.fake_ble, incidents=incidents)
    finally:
        runtime.stop()
        for sig, handler in previous.items():
            loop.remove_signal_handler(sig)
            signal.signal(sig, handler)
