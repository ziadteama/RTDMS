"""Quality scoring that gates fatigue inference without becoming a model feature."""

from __future__ import annotations

import numpy as np

from .config import QualityConfig
from .signal import FloatArray
from .types import QualityReason, QualityReport, QualityState, SensorStatus


def assess_quality(
    samples: FloatArray,
    *,
    packet_loss_fraction: float,
    artifact_fraction: float,
    valid_interval_count: int,
    status: SensorStatus,
    config: QualityConfig,
) -> QualityReport:
    """Combine transport, sensor, and interval checks into a conservative gate."""

    values = np.asarray(samples, dtype=np.float32).reshape(-1)
    clipping_fraction = (
        float(np.mean((values <= 1.0) | (values >= (1 << 18) - 2))) if values.size else 1.0
    )
    flatline = values.size < 2 or float(np.std(values)) < 1e-3
    reasons = QualityReason.NONE
    if packet_loss_fraction > config.max_good_packet_loss_fraction:
        reasons |= QualityReason.PACKET_LOSS
    if status & (
        SensorStatus.FIFO_OVERFLOW | SensorStatus.SENSOR_RESET | SensorStatus.CONTACT_LOST
    ):
        reasons |= QualityReason.SENSOR_FAULT
    if clipping_fraction > 0.005 or status & SensorStatus.SATURATED:
        reasons |= QualityReason.CLIPPING
    if artifact_fraction > config.max_good_artifact_fraction:
        reasons |= QualityReason.ARTIFACTS
    if valid_interval_count < 30:
        reasons |= QualityReason.INSUFFICIENT_BEATS
    if flatline:
        reasons |= QualityReason.FLATLINE
    penalties = (
        min(packet_loss_fraction / max(config.max_degraded_packet_loss_fraction, 1e-9), 1.0),
        min(artifact_fraction / max(config.max_degraded_artifact_fraction, 1e-9), 1.0),
        min(clipping_fraction / 0.01, 1.0),
        1.0 if status else 0.0,
        1.0 if flatline else 0.0,
    )
    score = max(0.0, 1.0 - sum(penalties) / len(penalties))
    if reasons & (QualityReason.SENSOR_FAULT | QualityReason.CLIPPING | QualityReason.FLATLINE):
        state = QualityState.BAD
    elif score >= config.good_score and not reasons:
        state = QualityState.GOOD
    elif score >= config.degraded_score and valid_interval_count >= 30:
        state = QualityState.DEGRADED
    else:
        state = QualityState.BAD
    return QualityReport(
        state=state,
        score=score,
        reasons=reasons,
        packet_loss_fraction=packet_loss_fraction,
        artifact_fraction=artifact_fraction,
        clipping_fraction=clipping_fraction,
        valid_interval_count=valid_interval_count,
    )
