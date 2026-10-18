"""Simple mode: one phone / drink / food detector, three box rules (rules.yaml `mode: simple`)
plus a texting rule for phones the camera cannot see.

    phone          a phone box in >= on_ratio of the last phone_window_s (1 s)       -> ALERT
    phone_in_hand  head pitched down from the drive's baseline + a pose wrist low and
                   central, held 2 s -> WARNING, 3 s -> ALERT (no phone box needed)
    drinking       a drink box overlapping the lower face (smoothed, 0.5 s)           -> ALERT
    eating         a food box overlapping the lower face (smoothed, 0.5 s)            -> ALERT

The lower face comes from the face mesh: nose tip down to the chin + below_chin fw, across the
face width + side_pad fw per side. A cup or hand that hides the face is common while drinking,
so the last face is reused for face_hold_s. With no face at all, drinking / eating are unknown
(None: the smoother holds its state) rather than false.
"""

from __future__ import annotations

import numpy as np

from .config import SIMPLE_BEHAVIOURS, SimpleRulesConfig, SmoothingConfig
from .rules import CHIN, DRIVER_LEFT_EAR, DRIVER_RIGHT_EAR, Baseline, face_scale
from .smoothing import BehaviourSmoother
from .types import Box, Detection, FaceObservation

NOSE_TIP = 1


def lower_face(face: FaceObservation, cfg: SimpleRulesConfig) -> Box:
    lm = face.landmarks
    fw = face_scale(face)
    xs = (lm[DRIVER_RIGHT_EAR][0], lm[DRIVER_LEFT_EAR][0])
    return Box(min(xs) - cfg.side_pad * fw, float(lm[NOSE_TIP][1]),
               max(xs) + cfg.side_pad * fw, float(lm[CHIN][1]) + cfg.below_chin * fw)


def overlaps(a: Box, b: Box) -> bool:
    return min(a.x2, b.x2) > max(a.x1, b.x1) and min(a.y2, b.y2) > max(a.y1, b.y1)


def wrist_low(kpts: np.ndarray | None, cfg: SimpleRulesConfig) -> bool | None:
    """A wrist low (lap / phone height) and central, in shoulder widths from the shoulders'
    midpoint. COCO-17: 5 / 6 shoulders, 9 / 10 wrists. None = shoulders not seen."""
    if kpts is None:
        return None
    k = np.asarray(kpts, np.float64)
    if k[5, 2] < cfg.texting_kp_conf or k[6, 2] < cfg.texting_kp_conf:
        return None
    sw = float(np.hypot(*(k[5, :2] - k[6, :2])))
    if sw < 1.0:
        return None
    mid = (k[5, :2] + k[6, :2]) / 2
    return any(k[j, 2] >= cfg.texting_kp_conf and k[j, 1] >= mid[1] + cfg.texting_wrist_low * sw
               and abs(k[j, 0] - mid[0]) <= cfg.texting_wrist_central * sw for j in (9, 10))


class TextingRule:
    """Head down + hand low, held: phone_in_hand without a phone box (rule A)."""

    def __init__(self, cfg: SimpleRulesConfig, baseline_s: float, baseline_n: int):
        self.cfg = cfg
        self.baseline = Baseline(baseline_s, baseline_n)
        self._since: float | None = None
        self._last_true = -1e9

    def update(self, t: float, face: FaceObservation | None,
               kpts: np.ndarray | None) -> tuple[str, float, str]:
        """-> (level, seconds held, why)."""
        down = False
        if face is not None:
            self.baseline.update(t, face)
            if self.baseline.ready and face.pitch_deg is not None:
                down = face.pitch_deg - self.baseline.pitch >= self.cfg.texting_pitch_deg
        cond = down and bool(wrist_low(kpts, self.cfg))
        if cond:
            self._last_true = t
            if self._since is None:
                self._since = t
        elif t - self._last_true > self.cfg.texting_gap_s:
            self._since = None
        if self._since is None:
            return "none", 0.0, ""
        held = t - self._since
        level = "alert" if held >= self.cfg.texting_alert_s else \
            "warning" if held >= self.cfg.texting_warn_s else "none"
        why = f"head down + hand low {held:.1f} s"
        return level, held, why


class SimpleRules:
    def __init__(self, cfg: SimpleRulesConfig, baseline_s: float = 10.0, baseline_n: int = 30):
        self.cfg = cfg
        self.texting = TextingRule(cfg, baseline_s, baseline_n) if cfg.texting else None

        def smoother(window_s: float) -> BehaviourSmoother:
            return BehaviourSmoother(SmoothingConfig(window_s=window_s, on_ratio=cfg.on_ratio,
                                                     off_ratio=cfg.off_ratio))

        self.smoothers = {"phone": smoother(cfg.phone_window_s),
                          "drinking": smoother(cfg.object_window_s),
                          "eating": smoother(cfg.object_window_s)}
        self._face: FaceObservation | None = None
        self._face_t = -1e9

    def update(self, t: float, face: FaceObservation | None, dets: list[Detection],
               kpts: np.ndarray | None = None) -> dict[str, dict]:
        """kpts: the driver's COCO-17 pose keypoints (17, 3) in view pixels, or None."""
        if face is not None:
            self._face, self._face_t = face, t
        held = self._face if t - self._face_t <= self.cfg.face_hold_s else None
        zone = lower_face(held, self.cfg) if held is not None else None

        def best(cls: str, near_mouth: bool) -> tuple[bool | None, float, str]:
            boxes = [d for d in dets if d.cls == cls]
            if near_mouth:
                if zone is None:
                    return None, 0.0, "no face"
                boxes = [d for d in boxes if overlaps(d.box, zone)]
            if not boxes:
                return False, 0.0, ""
            d = max(boxes, key=lambda d: d.conf)
            return True, d.conf, f"{cls} {d.conf:.2f}" + (" at the lower face" if near_mouth
                                                          else "")

        raw = {"phone": best("phone", False), "drinking": best("drink", True),
               "eating": best("food", True)}
        out = {}
        for b in SIMPLE_BEHAVIOURS:
            if b == "phone_in_hand":
                if self.texting is None:
                    continue
                level, held, why = self.texting.update(t, face, kpts)
                out[b] = {"active": level == "alert", "level": level, "confidence": 0.0,
                          "ratio": 0.0, "raw": held > 0, "holding": False, "why": why,
                          "held_s": round(held, 2)}
                continue
            active, conf, why = raw[b]
            s = self.smoothers[b].update(t, active, conf)
            level = "alert" if s.active else "none"
            out[b] = {"active": s.active, "level": level, "confidence": round(s.confidence, 3),
                      "ratio": round(s.ratio, 2), "raw": active, "holding": s.holding,
                      "why": why}
        return out

    @property
    def zone(self) -> Box | None:
        return lower_face(self._face, self.cfg) if self._face is not None else None
