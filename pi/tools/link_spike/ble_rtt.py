#!/usr/bin/env python3
"""BLE round-trip latency, notify loss, and reconnect benchmark client."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
import time
from pathlib import Path
from typing import Any

from rtdms_pi.ble.contract import CONTRACT_VERSION
from rtdms_pi.ble.uuids import Char
from rtdms_pi.payloads import to_json_bytes

tools_dir = Path(__file__).resolve().parents[1]
if str(tools_dir) not in sys.path:
    sys.path.insert(0, str(tools_dir))
from phone_sim_client import Results  # noqa: E402

from .metrics import calculate_notify_loss, calculate_percentiles  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="RTDMS-Pi")
    parser.add_argument("--token", default=os.getenv("RTDMS_TOKEN", ""))
    parser.add_argument("--samples", type=int, default=100, help="Command RTT samples")
    parser.add_argument("--notify-seconds", type=float, default=60.0, help="Stream loss test")
    parser.add_argument("--cycles", type=int, default=5, help="Reconnect cycles")
    return parser.parse_args()


async def run_benchmark(args: argparse.Namespace) -> None:
    bleak = importlib.import_module("bleak")
    token = args.token or os.getenv("RTDMS_TOKEN")
    if not token:
        raise ValueError("RTDMS_TOKEN environment variable or --token required")

    print(f"Scanning for {args.name}...")
    device = await bleak.BleakScanner.find_device_by_filter(
        lambda dev, adv: adv.local_name == args.name or dev.name == args.name, timeout=15
    )
    if device is None:
        raise RuntimeError(f"Pi device {args.name} not found")

    print(f"== Step 1: Measuring RTT over {args.samples} commands ==")
    results = Results()
    samples: list[float] = []
    async with bleak.BleakClient(device) as client:
        await client.write_gatt_char(
            Char.AUTH.uuid,
            to_json_bytes({"token": token, "contract": CONTRACT_VERSION}),
            response=True,
        )
        await client.write_gatt_char(
            Char.CLOCK.uuid,
            to_json_bytes({"phone_ms": time.time_ns() // 1_000_000}),
            response=True,
        )
        await client.start_notify(Char.RESULT.uuid, results.receive)

        for i in range(args.samples):
            try:
                lat = await results.command(client, i, "none")
                samples.append(lat)
            except Exception as e:
                print(f"Sample {i} failed: {e}")

        await client.stop_notify(Char.RESULT.uuid)

    if samples:
        p50, p95 = calculate_percentiles(samples)
        loss_pct = round(100.0 * (args.samples - len(samples)) / args.samples, 2)
        print(
            f"Command RTT: n={len(samples)}/{args.samples} "
            f"p50={p50:.2f}ms p95={p95:.2f}ms loss={loss_pct}%"
        )

    print(f"== Step 2: Measuring notify loss over {args.notify_seconds}s ==")
    alert_count = 0

    def alert_counter(sender: Any, raw: bytearray) -> None:
        nonlocal alert_count
        alert_count += 1

    async with bleak.BleakClient(device) as client:
        await client.write_gatt_char(
            Char.AUTH.uuid,
            to_json_bytes({"token": token, "contract": CONTRACT_VERSION}),
            response=True,
        )
        await client.start_notify(Char.ALERT.uuid, alert_counter)
        await asyncio.sleep(args.notify_seconds)
        await client.stop_notify(Char.ALERT.uuid)

    notify_loss = calculate_notify_loss(alert_count, args.notify_seconds, 5.0)
    print(f"Notify stream: received={alert_count} in {args.notify_seconds}s, loss={notify_loss}%")

    print(f"== Step 3: Measuring reconnect time over {args.cycles} cycles ==")
    reconnect_times: list[float] = []
    for _cycle in range(args.cycles):
        start = time.perf_counter()
        async with bleak.BleakClient(device) as client:
            await client.write_gatt_char(
                Char.AUTH.uuid,
                to_json_bytes({"token": token, "contract": CONTRACT_VERSION}),
                response=True,
            )
            reconnect_times.append((time.perf_counter() - start) * 1000)
        await asyncio.sleep(1.0)

    rec_p50, rec_p95 = calculate_percentiles(reconnect_times)
    print(
        f"Reconnect time: cycles={len(reconnect_times)} "
        f"p50={rec_p50:.2f}ms p95={rec_p95:.2f}ms"
    )


if __name__ == "__main__":
    asyncio.run(run_benchmark(arguments()))
