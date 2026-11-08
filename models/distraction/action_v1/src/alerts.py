"""Step 6: alert logic on top of the per-frame action classifier.

- call: the classifier says "call" in >= 70% of the frames of the last 2 s, AND
  (phone-in-hand probability at either ear > PHONE_P on average over the window
   OR the driver is talking: lip-gap standard deviation over the window > TALK_STD).
- hand_on_face: never raises a phone alert (it is simply not "call").
- texting / drinking / eating: the class in >= 70% of the frames of the last 1.5 s.
- v2 (hybrid): texting also needs the phone-in-hand probability on the lap crop > lap_p on
  average over its window (lap_p=None = off); `alerts` limits which alerts this logic raises.
- every alert also needs the class's mean probability over its window >= MIN_P[class]
  (tuned on SynDD-val, see DECISIONS.md D12; 0 = off).
A window only counts once it spans at least 80% of its length; a gap of more than 1 s with no
face frame clears the history. An alert stays on while its condition holds; a new onset needs
REFRACTORY seconds after the previous alert ended (so one long call = one event).
"""
from collections import deque

CLASSES = ["normal", "call", "texting", "drinking", "eating", "hand_on_face", "other"]
ALERTS = ("call", "texting", "drinking", "eating")
WIN = {"call": 2.0, "texting": 1.5, "drinking": 1.5, "eating": 1.5}
FRAC = 0.7
PHONE_P = 0.5
TALK_STD = 0.02  # tuned on SynDD-val in evaluate.py (lip gap / face width)
MIN_P = {"call": 0.0, "texting": 0.8, "drinking": 0.7, "eating": 0.7}  # D12
GAP = 1.0
REFRACTORY = 3.0


class AlertLogic:
    def __init__(self, phone_p=PHONE_P, talk_std=TALK_STD, use_phone=True, use_talk=True,
                 frac=FRAC, min_p=None, classes=CLASSES, alerts=ALERTS, lap_p=None):
        self.phone_p, self.talk_std = phone_p, talk_std
        self.use_phone, self.use_talk, self.frac = use_phone, use_talk, frac
        self.min_p = {**MIN_P, **(min_p or {})}
        self.classes, self.alerts, self.lap_p = list(classes), tuple(alerts), lap_p
        self.hist = deque()  # (t, cls index, phone prob, lip, class probs, lap phone prob)
        self.on = {a: False for a in self.alerts}
        self.off_t = {a: -1e9 for a in self.alerts}

    def reset(self):
        self.hist.clear()

    def _window(self, t, w):
        fr = [h for h in self.hist if t - h[0] <= w + 1e-6]
        if not fr or t - fr[0][0] < 0.8 * w - 1e-6:
            return None
        return fr

    def update(self, t, probs, phone, lip, lap=None):
        """probs: class probabilities in `classes` order; phone: max phone-in-hand prob over the
        two ears (or None); lip: lip gap / face width; lap: phone-in-hand prob on the lap crop.
        Returns {alert: bool} and the new onsets."""
        cls = max(range(len(probs)), key=lambda i: probs[i])
        if self.hist and t - self.hist[-1][0] > GAP:
            self.hist.clear()
        self.hist.append((t, cls, phone, lip, probs, lap))
        while self.hist and t - self.hist[0][0] > max(WIN.values()) + 1e-6:
            self.hist.popleft()
        state, onsets = {}, []
        for a in self.alerts:
            fr = self._window(t, WIN[a])
            ok = False
            if fr is not None:
                k = self.classes.index(a)
                ok = sum(h[1] == k for h in fr) >= self.frac * len(fr) and \
                    sum(h[4][k] for h in fr) / len(fr) >= self.min_p[a]
                if ok and a == "call" and (self.use_phone or self.use_talk):
                    ps = [h[2] for h in fr if h[2] is not None]
                    phone_ok = self.use_phone and bool(ps) and sum(ps) / len(ps) > self.phone_p
                    lips = [h[3] for h in fr]
                    m = sum(lips) / len(lips)
                    sd = (sum((x - m) ** 2 for x in lips) / len(lips)) ** 0.5
                    talk_ok = self.use_talk and len(lips) >= 3 and sd > self.talk_std
                    ok = phone_ok or talk_ok
                if ok and a == "texting" and self.lap_p is not None:
                    ls = [h[5] for h in fr if h[5] is not None]
                    ok = bool(ls) and sum(ls) / len(ls) > self.lap_p
            if ok and not self.on[a] and t - self.off_t[a] >= REFRACTORY:
                onsets.append(a)
                self.on[a] = True
            elif not ok and self.on[a]:
                self.on[a] = False
                self.off_t[a] = t
            state[a] = self.on[a]
        return state, onsets
