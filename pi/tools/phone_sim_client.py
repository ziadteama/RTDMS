#!/usr/bin/env python3
"""Laptop BLE central; requires the ble extra. Never used by verification gates."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib
import json
import math
import time
import uuid
from pathlib import Path
from typing import Any

from rtdms_pi.ble.contract import CONTRACT_VERSION
from rtdms_pi.ble.uuids import Char
from rtdms_pi.payloads import to_json_bytes


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="RTDMS-Pi")
    parser.add_argument("--token-file", type=Path, help="Otherwise prompt without echo")
    parser.add_argument("--test-alert", action="store_true")
    parser.add_argument("--incident", action="store_true")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--seconds", type=float, default=5)
    return parser.parse_args()


class Results:
    def __init__(self) -> None:
        self.pending: dict[str, tuple[float, asyncio.Future[float]]] = {}
        self.incident: asyncio.Future[dict[str, Any]] | None = None

    def receive(self, sender: Any, raw: bytearray) -> None:
        payload = json.loads(raw)
        print("result", payload)
        pending = self.pending.pop(payload.get("id", ""), None)
        if pending is not None:
            started, future = pending
            if not future.done():
                future.set_result((time.perf_counter() - started) * 1000)
        elif self.incident is not None and not self.incident.done():
            self.incident.set_result(payload)

    async def command(self, client: Any, index: int, pattern: str) -> float:
        key = f"sim{index}"
        future: asyncio.Future[float] = asyncio.get_running_loop().create_future()
        self.pending[key] = (time.perf_counter(), future)
        try:
            await client.write_gatt_char(
                Char.COMMAND.uuid,
                to_json_bytes({"cmd": "test_alert", "pattern": pattern, "id": key}),
                response=True,
            )
            return await asyncio.wait_for(future, 5)
        finally:
            self.pending.pop(key, None)


async def run(args: argparse.Namespace) -> None:
    bleak = importlib.import_module("bleak")
    token = args.token_file.read_text().strip() if args.token_file else getpass.getpass("Token: ")
    device = await bleak.BleakScanner.find_device_by_filter(
        lambda device, adv: adv.local_name == args.name or device.name == args.name, timeout=15
    )
    if device is None:
        raise RuntimeError("Pi not found")
    results = Results()
    async with bleak.BleakClient(device) as client:
        await client.write_gatt_char(
            Char.AUTH.uuid,
            to_json_bytes({"token": token, "contract": CONTRACT_VERSION}),
            response=True,
        )
        await client.write_gatt_char(
            Char.CLOCK.uuid, to_json_bytes({"phone_ms": time.time_ns() // 1_000_000}), response=True
        )
        await client.start_notify(Char.RESULT.uuid, results.receive)
        for char in (Char.ALERT, Char.STATUS, Char.PHYSIO):
            await client.start_notify(char.uuid, telemetry(char))
        samples = [
            await results.command(client, i, "max" if args.test_alert else "none")
            for i in range(args.samples)
        ]
        if args.incident:
            results.incident = asyncio.get_running_loop().create_future()
            await client.write_gatt_char(
                Char.INCIDENT.uuid,
                to_json_bytes(
                    {
                        "t_crash": time.time_ns() // 1_000_000,
                        "g_peak": 0,
                        "client_id": str(uuid.uuid4()),
                    }
                ),
                response=True,
            )
            await asyncio.wait_for(results.incident, 5)
        if samples:
            ordered = sorted(samples)
            p50, p95 = (ordered[math.ceil(len(ordered) * q) - 1] for q in (0.5, 0.95))
            print(f"write→result n={len(samples)} p50={p50:.2f}ms p95={p95:.2f}ms")
        await asyncio.sleep(args.seconds)


def telemetry(char: Char) -> Any:
    return lambda sender, raw: print(char.name.lower(), json.loads(raw))


if __name__ == "__main__":
    asyncio.run(run(arguments()))
