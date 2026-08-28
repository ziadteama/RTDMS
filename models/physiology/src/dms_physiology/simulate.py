"""Deterministic no-hardware synthetic PPG replay for pipeline verification."""

from __future__ import annotations

import argparse
import asyncio
import json
import math

from .acquisition import ReplaySource
from .fusion import InMemorySink
from .service import PhysiologyService
from .types import Channel, PpgFrame, PpgPacket, SensorStatus


def synthetic_frames(
    seconds: int, sample_rate_hz: int = 100, batch_size: int = 20
) -> tuple[PpgFrame, ...]:
    """Generate repeatable pulse-shaped raw PPG frames with known 60 bpm rhythm."""

    frames: list[PpgFrame] = []
    total = seconds * sample_rate_hz
    for sequence, start in enumerate(range(0, total, batch_size)):
        rows: list[tuple[int, ...]] = []
        for index in range(start, min(start + batch_size, total)):
            phase = (index % sample_rate_hz) / sample_rate_hz
            pulse = math.exp(-(((phase - 0.18) / 0.06) ** 2))
            drift = 500.0 * math.sin(index / sample_rate_hz / 20.0)
            rows.append((round(50_000 + drift + 18_000 * pulse),))
        packet = PpgPacket(
            version=1,
            sequence=sequence % (1 << 16),
            first_sample_index=start,
            channels=Channel.INFRARED,
            status=SensorStatus.NONE,
            samples=tuple(rows),
        )
        frames.append(
            PpgFrame(
                packet=packet,
                sample_rate_hz=sample_rate_hz,
                received_at_seconds=start / sample_rate_hz,
            )
        )
    return tuple(frames)


async def run(seconds: int, quiet: bool) -> None:
    sink = InMemorySink()
    await PhysiologyService(ReplaySource(synthetic_frames(seconds)), sink).run()
    if not quiet:
        for output in sink.outputs[-3:]:
            print(json.dumps(output, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=70)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.seconds <= 0:
        raise SystemExit("--seconds must be positive")
    asyncio.run(run(args.seconds, args.quiet))


if __name__ == "__main__":
    main()
