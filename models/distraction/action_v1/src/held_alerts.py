"""Drinking-only state machine; no integration into hybrid/stream in Phase B."""

from collections import deque
from statistics import median


class DrinkingRule:
    def __init__(self, p=0.8, x=10, window=0.5):
        self.p, self.x, self.window = p, x, window
        self.history = deque()
        self.baseline = deque(maxlen=300)
        self.start = None
        self.confirmed_since = None
        self.on = False
        self.off_t = -1e9
        self.last_t = None
        self.gaps = deque(maxlen=15)

    def update(self, t, near, cup_probability, pitch=None):
        if self.last_t is not None and t - self.last_t > 1:
            self.history.clear()
            self.start = None
        if self.last_t is not None and 0 < t - self.last_t <= 1:
            self.gaps.append(t - self.last_t)
        self.last_t = t
        # D31: the window must span >= 2.5 frame intervals, or a slow stream (3MDAD, 3 fps)
        # never holds two samples and can never confirm.
        window = max(self.window, 2.5 * median(self.gaps)) if self.gaps else self.window
        if pitch is not None and not near:
            self.baseline.append(float(pitch))
        eligible = near and cup_probability is not None and cup_probability > 0.5
        if not eligible:
            self.start = None
            self.history.clear()
        else:
            if self.start is None:
                self.start = t
            self.history.append((t, cup_probability))
        while self.history and t - self.history[0][0] > window + 1e-6:
            self.history.popleft()
        mean = sum(p for _, p in self.history) / len(self.history) if self.history else 0
        covered = len(self.history) >= 2 or (
            bool(self.history) and t - self.history[0][0] >= 0.8 * window - 1e-6
        )
        pitch_up = (
            pitch is not None
            and len(self.baseline) >= 10
            and median(self.baseline) - pitch >= self.x
        )
        confirmed = eligible and covered and mean > self.p
        if not confirmed:
            self.confirmed_since = None
        elif self.confirmed_since is None:
            self.confirmed_since = t
        sip = self.confirmed_since is not None and t - self.confirmed_since >= 0.5 - 1e-6
        active = confirmed and (pitch_up or sip)
        onset = active and not self.on and t - self.off_t >= 3
        if self.on and not active:
            self.off_t = t
        self.on = bool(active and (self.on or onset))
        return self.on, onset
