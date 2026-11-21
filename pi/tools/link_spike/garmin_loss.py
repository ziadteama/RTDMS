#!/usr/bin/env python3
"""Garmin packet loss parser and instructions for journald log inspection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .metrics import parse_garmin_loss

INSTRUCTIONS = """
=== Measuring Garmin Packet Loss on Raspberry Pi ===

Garmin packet counters are logged by `rtdms-pi` at service shutdown:
"[garmin] received N, lost M"

To extract counters:
1. Ensure the Garmin watch is connected and transmitting RR intervals.
2. Stop the runtime service cleanly:
   sudo systemctl stop rtdms-pi
3. Inspect the journald shutdown log line:
   journalctl -u rtdms-pi -n 50 | python3 pi/tools/link_spike/garmin_loss.py
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "logfile", nargs="?", type=Path, help="Path to log file or stdin if omitted"
    )
    parser.add_argument(
        "--instructions", action="store_true", help="Print step-by-step instructions"
    )
    args = parser.parse_args()

    if args.instructions or (args.logfile is None and sys.stdin.isatty()):
        print(INSTRUCTIONS.strip())
        return

    text = args.logfile.read_text(encoding="utf-8") if args.logfile else sys.stdin.read()
    try:
        received, lost, loss_pct = parse_garmin_loss(text)
        print(f"Garmin packets: received={received}, lost={lost}, loss_rate={loss_pct:.2f}%")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Tip: Run with --instructions for setup guide.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
