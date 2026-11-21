"""Pure metric calculations, parsing, and CSV row building for link spike."""

from __future__ import annotations

import math
import re


def calculate_percentiles(samples: list[float]) -> tuple[float, float]:
    if not samples:
        return 0.0, 0.0
    ordered = sorted(samples)
    n = len(ordered)
    p50 = ordered[max(0, math.ceil(n * 0.5) - 1)]
    p95 = ordered[max(0, math.ceil(n * 0.95) - 1)]
    return round(p50, 2), round(p95, 2)


def decode_throttled(text: str) -> int:
    match = re.search(r"throttled=(0x[0-9a-fA-F]+|[0-9]+)", text)
    if match:
        return int(match.group(1), 0)
    try:
        return int(text.strip(), 0)
    except ValueError:
        return 0


def build_csv_row(
    timestamp: float,
    uptime_s: int,
    throttled: int,
    temp_c: float,
    cpu_pct: float,
    fps: float,
    dmesg_errors: int,
) -> str:
    return (
        f"{timestamp:.1f},{uptime_s},{hex(throttled)},{temp_c:.1f},"
        f"{cpu_pct:.1f},{fps:.1f},{dmesg_errors}"
    )


def calculate_notify_loss(
    received_count: int,
    duration_s: float,
    expected_hz: float = 5.0,
) -> float:
    expected = duration_s * expected_hz
    if expected <= 0:
        return 0.0
    lost = max(0.0, expected - received_count)
    return round(100.0 * lost / expected, 2)


def parse_garmin_loss(log_text: str) -> tuple[int, int, float]:
    match = re.search(r"(?:\[garmin\]\s+)?received\s+(\d+),\s*lost\s+(\d+)", log_text)
    if not match:
        raise ValueError("no garmin log pattern found")
    received = int(match.group(1))
    lost = int(match.group(2))
    total = received + lost
    loss_pct = round(100.0 * lost / total, 2) if total > 0 else 0.0
    return received, lost, loss_pct
