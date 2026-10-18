"""Temporal smoothing: sliding time window + hysteresis, per behaviour.

A behaviour turns on when at least `on_ratio` of the frames in the last `window_s` seconds are
positive (and the window actually holds enough history), and turns off only when that share
falls to `off_ratio`. Between the two it keeps its state, which stops flicker at the threshold.

`None` samples (face lost / occluded) are not counted at all: the state is held. If they last
longer than `face_lost_hold_s` the behaviour is cleared, so an alert cannot stick forever on a
driver who has left the camera's view.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .config import SmoothingConfig


@dataclass
class Smoothed:
    active: bool
    ratio: float  # positive share of the current window
    confidence: float  # mean confidence of the positive frames in the window
    holding: bool  # last sample was None and the state is being held


class BehaviourSmoother:
    def __init__(self, cfg: SmoothingConfig):
        self.cfg = cfg
        self._buf: deque[tuple[float, bool, float]] = deque()
        self._last_known_t: float | None = None
        self.active = False

    def reset(self) -> None:
        self._buf.clear()
        self.active = False

    def update(self, t: float, value: bool | None, confidence: float = 0.0) -> Smoothed:
        c = self.cfg
        if value is None:
            if self._last_known_t is not None and t - self._last_known_t > c.face_lost_hold_s:
                self.reset()
            return self._state(holding=True)

        self._last_known_t = t
        self._buf.append((t, value, confidence))
        while t - self._buf[0][0] > c.window_s:
            self._buf.popleft()

        st = self._state(holding=False)
        coverage = (t - self._buf[0][0]) / c.window_s
        if not self.active and st.ratio >= c.on_ratio and coverage >= c.min_coverage:
            self.active = True
        elif self.active and st.ratio <= c.off_ratio:
            self.active = False
        st.active = self.active
        return st

    def _state(self, holding: bool) -> Smoothed:
        if not self._buf:
            return Smoothed(self.active, 0.0, 0.0, holding)
        pos = [conf for _, v, conf in self._buf if v]
        ratio = len(pos) / len(self._buf)
        conf = sum(pos) / len(pos) if pos else 0.0
        return Smoothed(self.active, ratio, conf, holding)
