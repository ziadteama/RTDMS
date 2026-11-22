#!/usr/bin/env python3
"""Run the real BLE service and flip the fused alert pattern from a model-like thread.

Pi-side companion of bench_link's alert latency check: the Pi has no camera in the bench, so the
decision never changes by itself. Stop rtdms-pi-user first (one GATT server per adapter).
The alert payload carries the Pi wall-clock `t` of the send; the central subtracts its clock offset.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import threading
import time
from pathlib import Path

from dms_fusion import AlertPattern, FusionDecision

from rtdms_pi.config import RuntimeConfig
from rtdms_pi.main import build_runtime
from rtdms_pi.ble.server import run_runtime_ble


def flip(runtime_state, period_s: float, stop: threading.Event, log: Path) -> None:  # type: ignore[no-untyped-def]
    for pattern in itertools.cycle([AlertPattern.MAX, AlertPattern.NONE]):
        if stop.wait(period_s):
            return
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"{pattern.value} {time.time():.6f}\n")
        runtime_state.set_decision(FusionDecision(pattern, ["bench"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", type=float, default=2.0)
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".local/state/rtdms")
    parser.add_argument("--log", type=Path, default=Path("/tmp/alert_flips.txt"))
    args = parser.parse_args()
    config = RuntimeConfig(state_dir=args.state_dir, ble=True)
    runtime = build_runtime(config, True)
    stop = threading.Event()
    threading.Thread(target=flip, args=(runtime.state, args.period, stop, args.log), daemon=True).start()
    try:
        asyncio.run(run_runtime_ble(config, runtime))
    finally:
        stop.set()
        time.sleep(0)


if __name__ == "__main__":
    main()
