"""Simple mode: one phone / drink / food detector, three rules (rules.yaml `mode: simple`).

    phone     a phone box in >= on_ratio of the last phone_window_s (1 s)   -> ALERT
    drinking  a drink box overlapping the lower face (smoothed, 0.5 s)       -> ALERT
    eating    a food box overlapping the lower face (smoothed, 0.5 s)        -> ALERT

The lower face comes from the face mesh: nose tip down to the chin + below_chin fw, across the
face width + side_pad fw per side. A cup or hand that hides the face is common while drinking,
so the last face is reused for face_hold_s. With no face at all, drinking / eating are unknown
(None: the smoother holds its state) rather than false.
"""

from __future__ import annotations

from .config import SIMPLE_BEHAVIOURS, SimpleRulesConfig, SmoothingConfig
from .rules import CHIN, DRIVER_LEFT_EAR, DRIVER_RIGHT_EAR, face_scale
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


class SimpleRules:
    def __init__(self, cfg: SimpleRulesConfig):
        self.cfg = cfg

        def smoother(window_s: float) -> BehaviourSmoother:
            return BehaviourSmoother(SmoothingConfig(window_s=window_s, on_ratio=cfg.on_ratio,
                                                     off_ratio=cfg.off_ratio))

        self.smoothers = {"phone": smoother(cfg.phone_window_s),
                          "drinking": smoother(cfg.object_window_s),
                          "eating": smoother(cfg.object_window_s)}
        self._face: FaceObservation | None = None
        self._face_t = -1e9

    def update(self, t: float, face: FaceObservation | None,
               dets: list[Detection]) -> dict[str, dict]:
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
