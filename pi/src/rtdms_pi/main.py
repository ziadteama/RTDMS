"""Runtime entry point. Numeric thread limits precede all model imports."""

from __future__ import annotations

import os


def main() -> None:
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"

    from .buzzer import (
        BuzzerBackend,
        ConsoleBuzzer,
        GpioBuzzer,
        GpioVibration,
        PatternPlayer,
        SilentBuzzer,
    )
    from .config import RuntimeConfig
    from .http_debug import DebugServer
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

    config = RuntimeConfig.from_args()
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
        GarminPhysioSource(config.physio_stale_s) if config.physiology else NullPhysioSource()
    )
    runtime = Runtime(source, physio, player, state, tick_rate=config.tick_rate)
    server: DebugServer | None = None
    try:
        server = DebugServer(state, player, config)
        server.start()
        runtime.run_forever()
    finally:
        if server:
            server.stop()
        runtime.stop()


if __name__ == "__main__":
    main()
