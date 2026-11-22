#!/usr/bin/env python3
"""Sample a Linux process using /proc, optionally with synthetic CPU load."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import FrameType
from typing import Any


@dataclass(frozen=True)
class ProcStat:
    cpu_ticks: int
    threads: int
    start_ticks: int


@dataclass(frozen=True)
class Sample:
    monotonic_s: float
    cpu_s: float
    rss_kib: int
    voluntary: int
    nonvoluntary: int
    threads: int
    start_ticks: int


def parse_stat(text: str) -> ProcStat:
    # comm (field 2) can contain spaces and parentheses; remaining fields cannot.
    end = text.rfind(")")
    if end < 0 or "(" not in text[:end]:
        raise ValueError("invalid stat comm")
    fields = text[end + 1:].split()  # Starts at field 3 (state).
    if len(fields) < 20:
        raise ValueError("truncated stat")
    return ProcStat(int(fields[11]) + int(fields[12]), int(fields[17]), int(fields[19]))


def parse_status(text: str) -> dict[str, int]:
    wanted = {"VmRSS", "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches"}
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key in wanted:
            values[key] = int(value.split()[0])
    if values.keys() != wanted:
        raise ValueError("missing process status fields (process may have exited)")
    return values


def read_sample(pid: int, ticks_per_second: int) -> Sample:
    root = Path("/proc") / str(pid)
    stat = parse_stat((root / "stat").read_text())
    status = parse_status((root / "status").read_text())
    return Sample(
        time.monotonic(), stat.cpu_ticks / ticks_per_second, status["VmRSS"],
        status["voluntary_ctxt_switches"], status["nonvoluntary_ctxt_switches"],
        stat.threads, stat.start_ticks,
    )


def compute_deltas(before: Sample, after: Sample) -> dict[str, float]:
    elapsed = after.monotonic_s - before.monotonic_s
    if elapsed <= 0 or before.start_ticks != after.start_ticks:
        raise ValueError("invalid interval or PID reused")
    if (after.cpu_s < before.cpu_s or after.voluntary < before.voluntary
            or after.nonvoluntary < before.nonvoluntary):
        raise ValueError("process counters moved backwards")
    return {
        "seconds": elapsed,
        "cpu_pct": 100 * (after.cpu_s - before.cpu_s) / elapsed,
        "voluntary_per_s": (after.voluntary - before.voluntary) / elapsed,
        "nonvoluntary_per_s": (after.nonvoluntary - before.nonvoluntary) / elapsed,
    }


def summarize(samples: list[Sample]) -> dict[str, Any]:
    if len(samples) < 2:
        raise ValueError("at least two samples required")
    intervals = [compute_deltas(a, b) for a, b in zip(samples, samples[1:], strict=False)]
    total = compute_deltas(samples[0], samples[-1])
    return {
        "duration_s": total["seconds"],
        "cpu_avg_pct": total["cpu_pct"],
        "cpu_max_pct": max(interval["cpu_pct"] for interval in intervals),
        "rss_start_mb": samples[0].rss_kib / 1024,
        "rss_end_mb": samples[-1].rss_kib / 1024,
        "rss_delta_mb": (samples[-1].rss_kib - samples[0].rss_kib) / 1024,
        "rss_unit": "MiB (1024 KiB)",
        "voluntary_per_s": total["voluntary_per_s"],
        "nonvoluntary_per_s": total["nonvoluntary_per_s"],
        "context_switch_scope": "process leader (/proc/PID/status)",
        "threads_start": samples[0].threads, "threads_end": samples[-1].threads,
        "threads_max": max(sample.threads for sample in samples),
        "intervals": intervals,
    }


def find_pid(name: str) -> int:
    matches = []
    for root in Path("/proc").iterdir():
        if not root.name.isdigit():
            continue
        try:
            comm = (root / "comm").read_text().strip()
            argv = (root / "cmdline").read_bytes().split(b"\0")
            executable = Path(os.fsdecode(argv[0])).name
            if name in (comm, executable):
                matches.append(int(root.name))
        except (OSError, ValueError):
            continue
    if len(matches) != 1:
        raise ValueError(f"expected exactly one process named {name!r}; found {len(matches)}")
    return matches[0]


def stop_signal(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def sample_process(pid: int, seconds: float, interval: float, load: int) -> list[Sample]:
    children: list[subprocess.Popen[bytes]] = []
    old_term = signal.signal(signal.SIGTERM, stop_signal)
    try:
        for _ in range(load):
            children.append(subprocess.Popen(
                [sys.executable, "-c", "while True: pass"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ))
        ticks = os.sysconf("SC_CLK_TCK")
        samples = [read_sample(pid, ticks)]
        deadline = samples[0].monotonic_s + seconds
        next_sample = min(samples[0].monotonic_s + interval, deadline)
        while samples[-1].monotonic_s < deadline:
            time.sleep(max(0, next_sample - time.monotonic()))
            samples.append(read_sample(pid, ticks))
            next_sample = min(samples[-1].monotonic_s + interval, deadline)
        return samples
    finally:
        # Ignore further termination requests while reaping all children.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        old_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            for child in children:
                if child.poll() is None:
                    child.kill()
            for child in children:
                child.wait()
        finally:
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGINT, old_int)


def positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pid", type=int)
    target.add_argument(
        "--pid-by-name", help="Exact /proc comm or executable basename; unique match",
    )
    parser.add_argument("--seconds", type=positive, default=60.0)
    parser.add_argument("--interval", type=positive, default=1.0)
    parser.add_argument("--load", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.load < 0 or (args.pid is not None and args.pid <= 0):
        parser.error("--load must be nonnegative and --pid must be positive")
    return args


def main() -> int:
    args = arguments()
    try:
        pid = args.pid if args.pid is not None else find_pid(args.pid_by_name)
        samples = sample_process(pid, args.seconds, args.interval, args.load)
        summary = summarize(samples)
        report = {"pid": pid, "load": args.load, "summary": summary,
                  "samples": [asdict(sample) for sample in samples]}
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; synthetic load children stopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
