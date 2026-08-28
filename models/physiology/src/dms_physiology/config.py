"""Immutable runtime configuration and validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FilterConfig:
    """Parameters for the causal PPG filter."""

    lowcut_hz: float = 0.5
    highcut_hz: float = 5.0
    order: int = 2


@dataclass(frozen=True, slots=True)
class QualityConfig:
    """Initial quality thresholds, calibrated later against public data."""

    good_score: float = 0.8
    degraded_score: float = 0.5
    max_good_packet_loss_fraction: float = 0.01
    max_degraded_packet_loss_fraction: float = 0.05
    max_good_artifact_fraction: float = 0.10
    max_degraded_artifact_fraction: float = 0.25


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Fixed-rate scheduling and bounded-memory settings."""

    sample_rate_hz: float = 100.0
    hr_update_seconds: float = 1.0
    feature_update_seconds: float = 5.0
    feature_window_seconds: float = 60.0
    baseline_window_seconds: float = 300.0
    raw_buffer_seconds: float = 120.0
    filter: FilterConfig = FilterConfig()
    quality: QualityConfig = QualityConfig()

    def __post_init__(self) -> None:
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.filter.lowcut_hz <= 0 or self.filter.highcut_hz <= self.filter.lowcut_hz:
            raise ValueError("filter cutoffs must be positive and ordered")
        if self.filter.highcut_hz >= self.sample_rate_hz / 2:
            raise ValueError("filter highcut_hz must be below Nyquist")
        if self.feature_window_seconds < 30:
            raise ValueError("feature_window_seconds must be at least 30 seconds")

    @property
    def raw_buffer_samples(self) -> int:
        return round(self.raw_buffer_seconds * self.sample_rate_hz)
