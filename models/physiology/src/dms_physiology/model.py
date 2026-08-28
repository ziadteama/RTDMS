"""Dependency-free deployment inference for an exported logistic-regression model."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LogisticModel:
    """A validated standardised binary logistic-regression artifact."""

    schema_version: int
    version: str
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    threshold: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported model schema version: {self.schema_version}")
        length = len(self.feature_names)
        if length == 0:
            raise ValueError("model must contain at least one feature")
        if len(set(self.feature_names)) != length:
            raise ValueError("model feature names must be unique")
        if not (length == len(self.means) == len(self.scales) == len(self.coefficients)):
            raise ValueError("model vectors must have equal length")
        values = (*self.means, *self.scales, *self.coefficients, self.intercept)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("model parameters must be finite")
        if any(scale <= 0 for scale in self.scales):
            raise ValueError("feature scales must be positive")
        if not 0 < self.threshold < 1:
            raise ValueError("threshold must be in (0, 1)")

    @classmethod
    def from_json_file(cls, path: Path) -> LogisticModel:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=int(payload["schema_version"]),
            version=str(payload["version"]),
            feature_names=tuple(str(name) for name in payload["feature_names"]),
            means=_float_tuple(payload["means"]),
            scales=_float_tuple(payload["scales"]),
            coefficients=_float_tuple(payload["coefficients"]),
            intercept=float(payload["intercept"]),
            threshold=float(payload["threshold"]),
        )

    def probability(self, features: Mapping[str, float]) -> float:
        score = self.intercept
        for name, mean, scale, coefficient in zip(
            self.feature_names, self.means, self.scales, self.coefficients, strict=True
        ):
            value = features.get(name)
            if value is None or not math.isfinite(value):
                raise ValueError(f"missing or non-finite model feature: {name}")
            score += coefficient * ((value - mean) / scale)
        if score >= 0:
            return 1.0 / (1.0 + math.exp(-score))
        exp_score = math.exp(score)
        return exp_score / (1.0 + exp_score)


def _float_tuple(values: Sequence[float | int | str]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)
