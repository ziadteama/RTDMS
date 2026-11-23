#!/usr/bin/env python3
"""Laptop BLE bench for contract v1.2; requires only stdlib and optional bleak."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import math
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from link_spike.metrics import calculate_percentiles  # noqa: E402

# Contract snapshot: checked against ble/uuids.py and phone_service.py by unit tests.
SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb"
NAMES = "alert status physio settings command result incident clock auth health watch_alert".split()
UUIDS = {name: f"1375193a-7edb-4a34-b3f2-18130239{i:04x}" for i, name in enumerate(NAMES, 1)}
UUIDS["garmin"] = "1375193a-7edb-4a34-b3f2-18130239c8a8"
PROPERTIES = {
    "alert": {"read", "notify"}, "status": {"read", "notify"},
    "physio": {"read", "notify"}, "settings": {"read", "write"},
    "command": {"write"}, "result": {"notify"}, "incident": {"write"},
    "clock": {"write"}, "auth": {"write"}, "health": {"read"}, "watch_alert": {"read", "notify"},
    "garmin": {"write", "write-without-response"},
}
STEPS = ("discovery", "before_auth", "notifications", "command_rtt", "alert_change", "reconnect")


def encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode()


def notification_metrics(
    events: list[tuple[float, int]], start: float, end: float
) -> dict[str, Any]:
    """Include observation edges so a stream that stalls cannot hide its final gap."""
    arrivals = [(t, size) for t, size in events if start <= t <= end]
    times = [start, *(t for t, _ in arrivals), end]
    return {
        "count": len(arrivals), "mean_hz": len(arrivals) / (end - start),
        "max_gap_s": max(b - a for a, b in zip(times, times[1:], strict=False)),
        "arrival_monotonic_s": [t for t, _ in arrivals],
        "payload_bytes": [size for _, size in arrivals],
    }


def check_services(services: Any) -> tuple[list[dict[str, Any]], list[str]]:
    listing = []
    found: dict[str, set[str]] = {}
    for service in services:
        chars = []
        for char in service.characteristics:
            props = sorted(char.properties)
            chars.append({"uuid": char.uuid, "properties": props})
            if service.uuid.lower() == SERVICE:
                found[char.uuid.lower()] = set(props)
        listing.append({"uuid": service.uuid, "characteristics": chars})
    errors = [name for name, uuid in UUIDS.items() if found.get(uuid) != PROPERTIES[name]]
    return listing, errors


class Notifications:
    def __init__(self) -> None:
        self.events: dict[str, list[tuple[float, int]]] = {
            name: [] for name in ("alert", "status", "physio", "result")
        }
        self.pending: dict[str, asyncio.Future[tuple[float, bool]]] = {}

    def callback(self, name: str) -> Callable[[Any, bytearray], None]:
        def receive(sender: Any, raw: bytearray) -> None:
            now = time.monotonic()
            self.events[name].append((now, len(raw)))
            if name != "result":
                return
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
                    return
                future = self.pending.get(payload["id"])
                if future is not None and not future.done():
                    future.set_result((now, payload.get("ok") is True))
            except (ValueError, UnicodeError):
                pass
        return receive

    async def command(self, client: Any, key: str) -> float:
        future: asyncio.Future[tuple[float, bool]] = asyncio.get_running_loop().create_future()
        self.pending[key] = future
        try:
            start = time.monotonic()
            async with asyncio.timeout(5):
                await client.write_gatt_char(
                    UUIDS["command"], encode({"cmd": "test_alert", "pattern": "none", "id": key}),
                    response=True,
                )
                arrival, ok = await future
            if not ok:
                raise ValueError("command result was unsuccessful")
            return (arrival - start) * 1000
        finally:
            self.pending.pop(key, None)


async def rejected_command(client: Any, error_type: type[Exception]) -> tuple[bool, str]:
    try:
        await client.write_gatt_char(
            UUIDS["command"], encode({"cmd": "test_alert", "pattern": "none", "id": "unauth"}),
            response=True,
        )
    except error_type as exc:
        text = str(exc)
        # A rejection is an authorization error with the link still up;
        # a drop or ATT 0x0e is a FAIL.
        ok = ("0x08" in text or "NotAuthorized" in text or "Not Authorized" in text) and bool(
            client.is_connected
        )
        return ok, text[:120]
    return False, "write accepted"


async def run_benchmark(args: argparse.Namespace, token: str) -> dict[str, Any]:
    report: dict[str, Any] = {"contract": "1.2", "adapter": "hci0", "steps": {}}
    steps = report["steps"]
    active = "discovery"
    client: Any = None

    def record(name: str, passed: bool, **details: Any) -> None:
        steps[name] = {"status": "PASS" if passed else "FAIL", **details}
        print(f"{name}: {steps[name]['status']}")

    try:
        bleak = importlib.import_module("bleak")
        error_type = importlib.import_module("bleak.exc").BleakError

        async def connect() -> Any:
            nonlocal client
            device = await bleak.BleakScanner.find_device_by_filter(
                lambda dev, adv: adv.local_name == args.name or dev.name == args.name,
                timeout=4, adapter="hci0",
            )
            if device is None:
                raise TimeoutError("device not found")
            client = bleak.BleakClient(device, adapter="hci0", timeout=4)
            await client.connect()
            return client

        async def auth() -> None:
            await client.write_gatt_char(
                UUIDS["auth"], encode({"token": token, "contract": 1}), response=True,
            )
            # Verify that auth actually unlocked protected writes.
            await client.write_gatt_char(
                UUIDS["clock"], encode({"phone_ms": time.time_ns() // 1_000_000}), response=True,
            )

        async with asyncio.timeout(15):
            await connect()
        listing, errors = check_services(client.services)
        record(active, not errors, services=listing, missing_or_wrong_properties=errors)
        # Only UUIDs and properties are reported, never values or exception messages.
        print(json.dumps(listing).replace(token, "[REDACTED]"))
        active = "before_auth"
        async with asyncio.timeout(10):
            rejected, reject_detail = await rejected_command(client, error_type)
            try:
                await client.read_gatt_char(UUIDS["alert"])
                alert_read = "allowed"
            except error_type:
                alert_read = "rejected"
        record(
            active, rejected, command_rejected=rejected, reject_detail=reject_detail,
            alert_read=alert_read,
        )
        active = "notifications"
        notifications = Notifications()
        async with asyncio.timeout(15):
            await auth()
            start = time.monotonic()
            for name in notifications.events:
                await client.start_notify(UUIDS[name], notifications.callback(name))
        await asyncio.sleep(args.notify_seconds)
        end = time.monotonic()
        stats = {
            name: notification_metrics(events, start, end)
            for name, events in notifications.events.items()
        }
        alert = stats["alert"]
        passed = (
            0.8 <= alert["mean_hz"] <= 1.3 and alert["max_gap_s"] <= 1.5
            and all(stat["mean_hz"] <= 2 for stat in stats.values())
        )
        record(active, passed, duration_s=end - start, characteristics=stats)
        active = "command_rtt"
        samples = []
        failures = 0
        for index in range(args.samples):
            try:
                samples.append(await notifications.command(client, f"bench{index}"))
            except Exception:
                failures += 1
        p50, p95 = calculate_percentiles(samples)
        record(active, failures == 0 and p95 < 100, count=len(samples), failures=failures,
               p50_ms=p50, p95_ms=p95, max_ms=max(samples, default=None))
        active = "alert_change"
        steps[active] = {
            "status": "not measurable",
            "reason": "handlers_command.handle_command calls player.test_pattern only; "
                      "test_alert does not change the decision published by alert.",
        }
        print("alert_change: not measurable")
        active = "reconnect"
        cycles = []
        for _ in range(args.cycles):
            started = time.monotonic()
            try:
                async with asyncio.timeout(5):
                    await client.disconnect()
                    await connect()
                    reset, _ = await rejected_command(client, error_type)
                    await auth()
                elapsed = time.monotonic() - started
                cycles.append({"seconds": elapsed, "auth_reset": reset,
                               "status": "PASS" if elapsed < 5 and reset else "FAIL"})
            except Exception:
                cycles.append({"seconds": time.monotonic() - started, "status": "FAIL"})
        record(active, all(cycle["status"] == "PASS" for cycle in cycles), cycles=cycles)
    except Exception:
        # Backend exceptions can contain writes (including credentials). Never serialize them.
        record(active, False, reason="operation failed or timed out; exception details suppressed")
    finally:
        if client is not None:
            try:
                async with asyncio.timeout(5):
                    await client.disconnect()
            except Exception:
                report["cleanup_failed"] = True
        for step in STEPS:
            if step not in steps:
                record(step, False, reason="not run because an earlier operation failed")
    report["passed"] = (
        all(step["status"] == "PASS" for step in steps.values())
        and not report.get("cleanup_failed", False)
    )
    return report


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="RTDMS-Pi")
    parser.add_argument("--notify-seconds", type=positive_float, default=30.0)
    parser.add_argument("--samples", type=positive_int, default=100)
    parser.add_argument("--cycles", type=positive_int, default=5)
    parser.add_argument("--out", type=Path, default=Path("results.json"))
    return parser.parse_args()


def main() -> int:
    args = arguments()
    token = os.environ.get("RTDMS_TOKEN", "")
    if not token:
        print("FAIL: RTDMS_TOKEN must be set")
        return 1
    # Bleak debug logs can include characteristic writes; suppress logging for this CLI.
    logging.disable(logging.CRITICAL)
    report = asyncio.run(run_benchmark(args, token))
    serialized = json.dumps(report, indent=2).replace(token, "[REDACTED]")
    try:
        args.out.write_text(serialized + "\n")
    except OSError:
        print("FAIL: could not write report")
        return 1
    print("\nStep             Result")
    for name, step in report["steps"].items():
        print(f"{name:17}{step['status']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
