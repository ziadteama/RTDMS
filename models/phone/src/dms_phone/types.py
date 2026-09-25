"""Fusion-facing types for the phone distraction package."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntFlag, StrEnum


class DistractionClass(StrEnum):
    SAFE = "safe"
    PHONE = "phone"
    EATING = "eating"


class OutputState(StrEnum):
    WARMUP = "warmup"
    VALID = "valid"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class QualityState(StrEnum):
    GOOD = "good"
    DEGRADED = "degraded"
    BAD = "bad"


class QualityReason(IntFlag):
    NONE = 0
    NO_MODEL = 1
    LOW_CONFIDENCE = 2
    BAD_INPUT = 4
    INFERENCE_ERROR = 8


@dataclass(frozen=True, slots=True)
class QualityReport:
    state: QualityState
    score: float
    reasons: QualityReason = QualityReason.NONE


@dataclass(frozen=True, slots=True)
class PhoneOutput:
    """Scores + quality for DMS fusion. Never contains an alert decision."""

    schema_version: int
    model_version: str
    t_mono: float
    state: OutputState
    quality: QualityReport
    phone_score: float | None
    eating_score: float | None
    top_class: DistractionClass | None
    sustained_phone_ms: float = 0.0
    sustained_eating_ms: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "model_version": self.model_version,
            "t_mono": self.t_mono,
            "state": self.state.value,
            "quality": {
                "state": self.quality.state.value,
                "score": self.quality.score,
                "reasons": int(self.quality.reasons),
            },
            "phone_score": self.phone_score,
            "eating_score": self.eating_score,
            "top_class": None if self.top_class is None else self.top_class.value,
            "sustained_phone_ms": self.sustained_phone_ms,
            "sustained_eating_ms": self.sustained_eating_ms,
            "reasons": list(self.reasons),
        }
