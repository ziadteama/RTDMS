"""Runtime entry point. Numeric thread limits precede all model imports."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from .config import RuntimeConfig
    from .runtime import Runtime


def build_runtime(
    config: RuntimeConfig,
    ble: bool,
    settings_provider: Callable[[], Mapping[str, Any]] | None = None,
) -> Runtime:
    from .buzzer import (
        BuzzerBackend,
        ConsoleBuzzer,
        GpioBuzzer,
        GpioVibration,
        PatternPlayer,
        SilentBuzzer,
    )
    from .runtime import Runtime
    from .sources import (
        FrameSource,
        GarminPhysioSource,
        NullPhysioSource,
        PhysioSource,
        ScriptedFrameSource,
        StreamPipelineSource,
    )
    from .state import RuntimeState

    backend: BuzzerBackend
    if config.buzzer == "gpio":
        backend = GpioBuzzer(config.buzzer_pin)
    elif config.buzzer == "console":
        backend = ConsoleBuzzer()
    else:
        backend = SilentBuzzer()
    vibration = GpioVibration(config.vibration_pin) if config.vibration_pin is not None else None
    player = PatternPlayer(backend, vibration)
    state = RuntimeState(config.stale_s, config.physio_stale_s)
    source: FrameSource = (
        ScriptedFrameSource([]) if config.no_camera else StreamPipelineSource(config)
    )
    physio: PhysioSource = (
        GarminPhysioSource(config.physio_stale_s)
        if config.physiology or ble
        else NullPhysioSource()
    )
    return Runtime(
        source,
        physio,
        player,
        state,
        tick_rate=config.tick_rate,
        settings_provider=settings_provider,
    )


def main() -> None:
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    from .config import RuntimeConfig
    from .health import HealthProbe
    from .http_debug import DebugServer
    from .incidents.http_server import serve as serve_incidents
    from .incidents.ring import Entry, FrameRing
    from .incidents.sink import RingIncidentSink
    from .incidents.store import IncidentStore
    from .pairing import load_or_create_token
    from .payloads import alert_payload, status_payload
    from .settings import SettingsStore

    config = RuntimeConfig.from_args()
    ble = (
        config.ble
        if config.ble is not None
        else (not config.no_camera and importlib.util.find_spec("bless") is not None)
    )
    ble = ble or config.fake_ble
    settings_store = SettingsStore(config.state_dir / "settings.json")
    runtime = build_runtime(config, ble, settings_provider=settings_store.read)

    token = load_or_create_token(config.state_dir / "token")
    store = IncidentStore(config.state_dir / "incidents")
    ring = FrameRing(seconds=25.0, fps=10.0)
    sink = RingIncidentSink(ring=ring, store=store)

    orig_start = runtime.frame_source.start
    last_ring_push = 0.0

    def start_with_ring(on_frame: Any) -> None:
        def on_frame_wrapper(frame: Any) -> None:
            on_frame(frame)
            nonlocal last_ring_push
            now = time.monotonic()
            if now - last_ring_push >= 0.1:  # <= 10 fps
                last_ring_push = now
                s = runtime.state.snapshot()
                # TODO(P5-wiring): jpeg from stream Shared
                ring.push(
                    Entry(
                        t_mono=now,
                        t_wall=time.time(),
                        jpeg=None,
                        status=status_payload(s),
                        alert=alert_payload(s.decision, time.time()),
                    )
                )

        orig_start(on_frame_wrapper)

    runtime.frame_source.start = start_with_ring  # type: ignore[method-assign]

    debug_server: DebugServer | None = None
    incident_server = None
    try:
        health_probe = HealthProbe(
            state=runtime.state,
            settings_provider=settings_store.read,
            physio_source=runtime.physio_source,
            config=config,
            state_dir=config.state_dir,
        )
        debug_server = DebugServer(
            runtime.state,
            runtime.player,
            config,
            settings_provider=settings_store.read,
            health_probe=health_probe,
        )
        debug_server.start()
        incident_server = serve_incidents(config.host, config.incident_port, store, sink, token)
        if ble:
            from .ble.server import run_runtime_ble

            asyncio.run(
                run_runtime_ble(
                    config, runtime, incidents=sink, settings=settings_store
                )
            )
        else:
            runtime.run_forever()
    finally:
        if incident_server:
            incident_server.stop()
        if debug_server:
            debug_server.stop()
        runtime.stop()


if __name__ == "__main__":
    main()
