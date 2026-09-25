"""Stateful phone distraction pipeline → PhoneOutput for fusion."""

from __future__ import annotations

import time

import numpy as np

from .config import Config
from .detector import DetectResult, StubDetector, make_detector
from .types import (
    DistractionClass,
    OutputState,
    PhoneOutput,
    QualityState,
)


class PhonePipeline:
    def __init__(self, cfg: Config | None = None, detector: StubDetector | None = None) -> None:
        self.cfg = cfg or Config()
        self.detector = detector or make_detector(self.cfg.detector)
        self._phone_since: float | None = None
        self._eating_since: float | None = None
        self._last_infer = 0.0

    def process(self, frame_bgr: np.ndarray | None, *, now: float | None = None) -> PhoneOutput | None:
        """Run at most infer_hz. Returns None when this tick is skipped (rate limit)."""
        t = time.monotonic() if now is None else now
        period = 1.0 / max(self.cfg.detector.infer_hz, 0.1)
        if self._last_infer and (t - self._last_infer) < period:
            return None
        self._last_infer = t

        result = self.detector.predict(frame_bgr)
        return self._to_output(result, t)

    def _to_output(self, result: DetectResult, now: float) -> PhoneOutput:
        q = result.quality
        if q.state is QualityState.BAD:
            self._phone_since = None
            self._eating_since = None
            return PhoneOutput(
                schema_version=self.cfg.schema_version,
                model_version=self.cfg.detector.model_version,
                t_mono=now,
                state=OutputState.UNAVAILABLE,
                quality=q,
                phone_score=None,
                eating_score=None,
                top_class=None,
                reasons=["quality gate blocked scores"],
            )

        phone_p = result.probs.get(DistractionClass.PHONE, 0.0)
        eating_p = result.probs.get(DistractionClass.EATING, 0.0)
        safe_p = result.probs.get(DistractionClass.SAFE, 0.0)
        top = max(
            (safe_p, DistractionClass.SAFE),
            (phone_p, DistractionClass.PHONE),
            (eating_p, DistractionClass.EATING),
            key=lambda x: x[0],
        )[1]

        if phone_p >= self.cfg.detector.phone_threshold:
            if self._phone_since is None:
                self._phone_since = now
        else:
            self._phone_since = None

        if eating_p >= self.cfg.detector.eating_threshold:
            if self._eating_since is None:
                self._eating_since = now
        else:
            self._eating_since = None

        sustained_phone = 0.0 if self._phone_since is None else (now - self._phone_since) * 1000.0
        sustained_eating = 0.0 if self._eating_since is None else (now - self._eating_since) * 1000.0

        state = OutputState.VALID
        if q.state is QualityState.DEGRADED:
            state = OutputState.DEGRADED

        return PhoneOutput(
            schema_version=self.cfg.schema_version,
            model_version=self.cfg.detector.model_version,
            t_mono=now,
            state=state,
            quality=q,
            phone_score=phone_p,
            eating_score=eating_p,
            top_class=top,
            sustained_phone_ms=sustained_phone,
            sustained_eating_ms=sustained_eating,
            reasons=[f"backend={result.backend}"],
        )
