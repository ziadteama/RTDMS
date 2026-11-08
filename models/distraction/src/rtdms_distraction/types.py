"""Plain data passed between stages. All coordinates are pixels in the rectified driver view."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def w(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def h(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def cx(self) -> float:
        return 0.5 * (self.x1 + self.x2)

    @property
    def cy(self) -> float:
        return 0.5 * (self.y1 + self.y2)

    @classmethod
    def around(cls, cx: float, cy: float, half_w: float, half_h: float) -> Box:
        return cls(cx - half_w, cy - half_h, cx + half_w, cy + half_h)

    def as_list(self) -> list[float]:
        return [round(self.x1, 1), round(self.y1, 1), round(self.x2, 1), round(self.y2, 1)]


def intersection(a: Box, b: Box) -> float:
    w = min(a.x2, b.x2) - max(a.x1, b.x1)
    h = min(a.y2, b.y2) - max(a.y1, b.y1)
    return w * h if w > 0 and h > 0 else 0.0


def overlap_min(a: Box, b: Box) -> float:
    """Intersection over the smaller area. 1.0 when one box is inside the other.

    Used instead of IoU because a phone is much smaller than an ear zone, and a phone held at
    the far ear is often only partly visible: IoU would punish both.
    """
    denom = min(a.area, b.area)
    return intersection(a, b) / denom if denom > 0 else 0.0


def box_gap(a: Box, b: Box) -> float:
    """Euclidean gap between two boxes; 0 when they touch or overlap."""
    dx = max(0.0, max(a.x1, b.x1) - min(a.x2, b.x2))
    dy = max(0.0, max(a.y1, b.y1) - min(a.y2, b.y2))
    return float(np.hypot(dx, dy))


def point_box_dist(px: float, py: float, b: Box) -> float:
    dx = max(b.x1 - px, 0.0, px - b.x2)
    dy = max(b.y1 - py, 0.0, py - b.y2)
    return float(np.hypot(dx, dy))


@dataclass(frozen=True)
class Detection:
    cls: str  # phone | drink | food | hand
    conf: float
    box: Box
    source: str = "detector"  # detector | mediapipe_hands


@dataclass
class FaceObservation:
    """One face-mesh result, already reduced to what the rules need."""

    landmarks: np.ndarray  # (N, 2) pixels
    pitch_deg: float | None  # positive = head down (chin toward chest)
    yaw_deg: float | None  # positive = face turned toward image-right
    gaze_down: float | None  # larger = looking further down
    gaze_source: str  # blendshape | iris | none
    jaw_open: float | None  # blendshape jawOpen (0..1) or geometric chin-nose distance in fw
    jaw_source: str  # blendshape | geometric
    lip_ratio: float  # inner-lip gap / mouth width
    blendshapes: dict[str, float] = field(default_factory=dict)

    def pt(self, i: int) -> np.ndarray:
        return self.landmarks[i]

    @property
    def face_width(self) -> float:
        return float(np.linalg.norm(self.landmarks[454] - self.landmarks[234]))

    @property
    def mouth_center(self) -> np.ndarray:
        return self.landmarks[[13, 14, 61, 291]].mean(axis=0)

    @property
    def center(self) -> np.ndarray:
        return 0.5 * (self.landmarks[234] + self.landmarks[454])
