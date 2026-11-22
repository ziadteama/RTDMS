"""Drive-time break reminder: the strongest fatigue predictor we found is time spent driving.

On MPD-DF, elapsed drive time predicted physician-rated fatigue better than heart rate (AUROC
0.84 vs 0.76). This is time on task, not physiology, and is labelled as such. A drive starts at
the first face seen after the driver has been away for `away_reset_s`; the reminder pulses for
`pulse_s` at `first_s` and then every `repeat_s`.
"""

from __future__ import annotations


class BreakReminder:
    def __init__(
        self,
        first_s: float = 2 * 3600.0,
        repeat_s: float = 30 * 60.0,
        pulse_s: float = 3.0,
        away_reset_s: float = 10 * 60.0,
    ) -> None:
        self.first_s, self.repeat_s = first_s, repeat_s
        self.pulse_s, self.away_reset_s = pulse_s, away_reset_s
        self._start: float | None = None
        self._last_face: float | None = None

    def due(self, now: float, face_present: bool) -> bool:
        """True while a reminder pulse is active."""
        if face_present:
            if self._last_face is None or now - self._last_face >= self.away_reset_s:
                self._start = now
            self._last_face = now
        if self._start is None or self._last_face is None:
            return False
        if now - self._last_face >= self.away_reset_s:
            self._start = None
            return False
        driven = now - self._start
        if driven < self.first_s:
            return False
        return (driven - self.first_s) % self.repeat_s < self.pulse_s

    def driven_s(self, now: float) -> float | None:
        return None if self._start is None else now - self._start
