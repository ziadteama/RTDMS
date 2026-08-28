"""Measure the physiology process during a deterministic replay on the target Pi."""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=7_200)
    args = parser.parse_args()
    command = ["dms-physiology-simulate", "--seconds", str(args.seconds), "--quiet"]
    started = time.perf_counter()
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    report = {
        "command": command,
        "exit_code": result.returncode,
        "wall_seconds": elapsed,
        "child_user_cpu_seconds": usage.ru_utime,
        "child_system_cpu_seconds": usage.ru_stime,
        "max_rss_kib": usage.ru_maxrss,
        "pid": os.getpid(),
        "stdout": result.stdout[-2_000:],
        "stderr": result.stderr[-2_000:],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
