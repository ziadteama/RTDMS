"""Time-domain HR and PRV features for a clean interval window."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .signal import Interval


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    """Features emitted to fusion and optional fatigue inference."""

    mean_hr_bpm: float
    hr_slope_bpm_per_min: float
    median_ibi_ms: float
    rmssd_ms: float
    sdnn_ms: float
    pnn50: float
    cvnn: float
    valid_interval_count: int
    artifact_fraction: float

    def model_features(self) -> dict[str, float]:
        return {
            "mean_hr_bpm": self.mean_hr_bpm,
            "hr_slope_bpm_per_min": self.hr_slope_bpm_per_min,
            "median_ibi_ms": self.median_ibi_ms,
            "log_rmssd": math.log1p(self.rmssd_ms),
            "sdnn_ms": self.sdnn_ms,
            "pnn50": self.pnn50,
            "cvnn": self.cvnn,
        }


def extract_features(intervals: tuple[Interval, ...]) -> FeatureSnapshot | None:
    """Calculate primary features from valid intervals without interpolation."""

    valid = np.asarray([item.duration_ms for item in intervals if item.valid], dtype=float)
    if valid.size < 3:
        return None
    successive = np.diff(valid)
    rmssd = float(np.sqrt(np.mean(np.square(successive)))) if successive.size else 0.0
    sdnn = float(np.std(valid, ddof=1)) if valid.size > 1 else 0.0
    pnn50 = float(np.mean(np.abs(successive) > 50.0)) if successive.size else 0.0
    heart_rates = 60_000.0 / valid
    slope = float(np.polyfit(np.arange(heart_rates.size), heart_rates, 1)[0] * 60.0 / valid.size)
    total = len(intervals)
    return FeatureSnapshot(
        mean_hr_bpm=float(np.mean(heart_rates)),
        hr_slope_bpm_per_min=slope,
        median_ibi_ms=float(np.median(valid)),
        rmssd_ms=rmssd,
        sdnn_ms=sdnn,
        pnn50=pnn50,
        cvnn=sdnn / float(np.mean(valid)),
        valid_interval_count=int(valid.size),
        artifact_fraction=0.0 if total == 0 else 1.0 - valid.size / total,
    )
