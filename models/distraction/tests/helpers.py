"""Synthetic faces and detections for rule tests (no network, no camera)."""

from __future__ import annotations

import numpy as np

from rtdms_distraction.config import RulesConfig
from rtdms_distraction.rules import HEIGHT_PER_WIDTH, RuleEngine
from rtdms_distraction.types import Box, Detection, FaceObservation


def make_face(cx: float = 320.0, cy: float = 260.0, fw: float = 120.0, *, pitch: float = 0.0,
              yaw: float = 0.0, gaze: float = 0.0, jaw: float = 0.1, lip: float = 0.02,
              jaw_source: str = "blendshape") -> FaceObservation:
    """A frontal face of width `fw` centred at (cx, cy). Driver faces the camera, so the
    driver's RIGHT ear (234) is on image-LEFT and the LEFT ear (454) on image-RIGHT."""
    lm = np.zeros((478, 2))
    half_h = fw * HEIGHT_PER_WIDTH / 2
    lm[234] = (cx - fw / 2, cy)
    lm[454] = (cx + fw / 2, cy)
    lm[10] = (cx, cy - half_h)
    lm[152] = (cx, cy + half_h)
    mouth_y = cy + 0.28 * fw
    mw = 0.4 * fw
    lm[61] = (cx - mw / 2, mouth_y)
    lm[291] = (cx + mw / 2, mouth_y)
    lm[13] = (cx, mouth_y - lip * mw / 2)
    lm[14] = (cx, mouth_y + lip * mw / 2)
    lm[1] = (cx, cy + 0.05 * fw)
    for i, (x, y) in {33: (-0.32, -0.15), 133: (-0.12, -0.15), 362: (0.12, -0.15),
                      263: (0.32, -0.15), 468: (-0.22, -0.15), 473: (0.22, -0.15),
                      172: (-0.38, 0.35), 397: (0.38, 0.35)}.items():
        lm[i] = (cx + x * fw, cy + y * fw)
    return FaceObservation(landmarks=lm, pitch_deg=pitch, yaw_deg=yaw, gaze_down=gaze,
                           gaze_source="blendshape", jaw_open=jaw, jaw_source=jaw_source,
                           lip_ratio=lip)


def det(cls: str, cx: float, cy: float, w: float, h: float, conf: float = 0.8) -> Detection:
    return Detection(cls, conf, Box.around(cx, cy, w / 2, h / 2))


def engine(driver_side: str = "right", hands: bool = True, cfg: RulesConfig | None = None,
           baseline_s: float = 0.0, min_samples: int = 1) -> RuleEngine:
    cfg = cfg or RulesConfig()
    cfg.baseline.duration_s = baseline_s
    cfg.baseline.min_samples = min_samples
    return RuleEngine(cfg, driver_side, hands, (640, 640))
