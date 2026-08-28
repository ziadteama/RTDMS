"""Deterministic no-hardware synthetic PPG replay for pipeline verification."""

from __future__ import annotations

import argparse
import asyncio
import json
import math

from .acquisition import ReplaySource
from .fusion import InMemorySink
from .service import PhysiologyService
from .types import PpgFrame


def synthetic_frames(
    seconds: int, sample_rate_hz: int = 100, batch_size: int = 20
) -> tuple[PpgFrame, ...]:
    """Generate repeatable pulse-shaped raw PPG frames with known 60 bpm rhythm."""

    from .waveform import WaveformConfig, generate_ppg

    config = WaveformConfig(
        seconds=float(seconds),
        sample_rate_hz=float(sample_rate_hz),
        batch_size=batch_size,
        hr_constant=60.0,
        baseline_drift=True,
        baseline_drift_amplitude=500.0,
        baseline_drift_frequency=1.0 / (40.0 * math.pi),
        seed=42,
    )

    frames: list[PpgFrame] = []
    for packet, _ in generate_ppg(config):
        frames.append(
            PpgFrame(
                packet=packet,
                sample_rate_hz=sample_rate_hz,
                received_at_seconds=packet.first_sample_index / sample_rate_hz,
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
