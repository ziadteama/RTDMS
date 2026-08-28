"""Replay BIDMC CSV PPG through the service and compare it with ECG-derived HR.

Download one record from PhysioNet's BIDMC PPG and Respiration Dataset first:
https://physionet.org/content/bidmc/1.0.0/
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

import numpy as np

from dms_physiology.acquisition import ReplaySource
from dms_physiology.config import RuntimeConfig
from dms_physiology.fusion import InMemorySink
from dms_physiology.service import PhysiologyService
from dms_physiology.types import Channel, PpgFrame, PpgPacket, SensorStatus


def load_pleth(path: Path) -> np.ndarray:
    with path.open(newline="", encoding="utf-8") as handle:
        return np.asarray([float(row[" PLETH"]) for row in csv.DictReader(handle)], dtype=float)


def load_hr(path: Path) -> np.ndarray:
    with path.open(newline="", encoding="utf-8") as handle:
        return np.asarray([float(row[" HR"]) for row in csv.DictReader(handle)], dtype=float)


def frames_from_pleth(pleth: np.ndarray, sample_rate_hz: int = 125) -> tuple[PpgFrame, ...]:
    scaled = 20_000.0 + 200_000.0 * (pleth - pleth.min()) / (pleth.max() - pleth.min())
    batch_size = 25
    frames: list[PpgFrame] = []
    for sequence, start in enumerate(range(0, scaled.size, batch_size)):
        samples = tuple((int(value),) for value in scaled[start : start + batch_size])
        packet = PpgPacket(
            version=1,
            sequence=sequence,
            first_sample_index=start,
            channels=Channel.INFRARED,
            status=SensorStatus.NONE,
            samples=samples,
        )
        frames.append(PpgFrame(packet, sample_rate_hz, start / sample_rate_hz))
    return tuple(frames)


async def validate(signals: Path, numerics: Path) -> dict[str, float | int]:
    sample_rate_hz = 125
    pleth = load_pleth(signals)
    reference_hr = load_hr(numerics)
    sink = InMemorySink()
    config = RuntimeConfig(sample_rate_hz=sample_rate_hz)
    await PhysiologyService(ReplaySource(frames_from_pleth(pleth)), sink, config).run()
    errors: list[float] = []
    for output in sink.outputs:
        estimated = output["mean_hr_bpm"]
        if output["state"] not in {"good", "degraded"} or estimated is None:
            continue
        end_second = int(output["window_end_sample_index"]) // sample_rate_hz
        second = min(end_second, len(reference_hr) - 1)
        errors.append(abs(float(estimated) - reference_hr[second]))
    if not errors:
        raise RuntimeError("the replay produced no quality-gated HR outputs")
    return {
        "samples": int(pleth.size),
        "duration_seconds": int(pleth.size // sample_rate_hz),
        "evaluated_outputs": len(errors),
        "hr_mae_bpm": float(np.mean(errors)),
        "hr_p95_absolute_error_bpm": float(np.percentile(errors, 95)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("signals", type=Path)
    parser.add_argument("numerics", type=Path)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(validate(args.signals, args.numerics)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
