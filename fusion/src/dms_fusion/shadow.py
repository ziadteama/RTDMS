"""Shadow-mode bookkeeping for the heart-rate fatigue score: logged, never acted on.

The score (a logistic over heart rate vs the driver's own baseline and its trend, trained on
MPD-DF) is too weak to change alerts. These counters show, per drive, how often it would have
agreed with the camera, so a later paired test can decide whether it deserves any weight.
Counts are per episode (rising edges), not per frame, and hold no heart-rate values.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import AlertPattern

SHADOW_THRESHOLD = 0.7


@dataclass(frozen=True, slots=True)
class ShadowCounts:
    agree: int = 0  # camera alert episode while the score was high
    disagree: int = 0  # camera alert episode while the score was low
    shadow_only: int = 0  # score went high with no camera alert


class ShadowTracker:
    def __init__(self, threshold: float = SHADOW_THRESHOLD) -> None:
        self.threshold = threshold
        self._counts = ShadowCounts()
        self._alert_on = False
        self._high_on = False

    @property
    def counts(self) -> ShadowCounts:
        return self._counts

    def observe(self, pattern: AlertPattern, score: float | None) -> None:
        """`score` None (no good heart-rate data) is skipped: it neither agrees nor disagrees."""
        alert = pattern in (AlertPattern.REPEATED, AlertPattern.CONTINUOUS, AlertPattern.MAX)
        high = score is not None and score >= self.threshold
        c = self._counts
        if alert and not self._alert_on and score is not None:
            c = ShadowCounts(c.agree + high, c.disagree + (not high), c.shadow_only)
        if high and not self._high_on and not alert:
            c = ShadowCounts(c.agree, c.disagree, c.shadow_only + 1)
        self._counts, self._alert_on, self._high_on = c, alert, high
