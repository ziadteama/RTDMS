"""Drinking for the live stream: stream.py --held.

Hand at the mouth + something in the hand -> DRINKING (IR product; eating not reported):

- pose (YOLO26n-pose 320, NCNN) ~6.7 / s gives the wrists;
- hand within K = 1.25 face heights of the mouth -> a hand-weighted square that also covers the
  bottle body (not the old face-centred 2× face-height box);
- held_food3.onnx on that 128 px grey crop: cup_bottle / empty_hand / food; P(cup)+P(food) is the
  object score. Alert name is always drinking.
- ON when >= 3 of the last 5 samples have an object (threshold from held_params.json p); OFF at
  <= 1 of 5. Phone veto while call/texting is on OR the ear crop already sees a phone (> 0.5).

OpenCV DNN for the ONNX cup model (the Pi has no onnxruntime).
"""

from __future__ import annotations

import json
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

DIST = Path(__file__).resolve().parents[1]
sys.path.append(str(DIST / "action_v1" / "src"))  # after scripts/: action_v1/src has its own hybrid.py etc.

from held_runtime import H, K, pose_mouth, square_cover  # noqa: E402

from rtdms_distraction.config import PoseConfig  # noqa: E402
from rtdms_distraction.pose import PoseEstimator, driver_person  # noqa: E402

POSE_DT = 0.15  # pose + cup check ~6.7 / s (was 10 / s; frees Pi headroom for the stream)
P_OBJECT_DEFAULT = 0.5  # product IR-4 value in held_params.json; SynDD food3 sweep used 0.95
WIN, ON_N, OFF_N = 5, 3, 1
# Crop was mouth↔wrist midpoint at 2× face height: the bottle body fell outside → object ~0.
# Hand-weighted, taller box keeps the bottle in the 128 px patch on this IR mount.
HAND_W, DOWN_FH, SIDE_FH, SIDE_DIST = 0.75, 0.25, 2.8, 1.8


def grip_crop(kp, mouth, fh):
    """Distance + square covering the grip and bottle, not just the face."""
    mouth = np.asarray(mouth, dtype=np.float64)
    best = None
    for elbow, wrist in ((7, 9), (8, 10)):
        if kp[wrist, 2] < 0.3:
            continue
        point = kp[wrist, :2].astype(np.float64).copy()
        if kp[elbow, 2] >= 0.3:
            point = point + H * (kp[wrist, :2] - kp[elbow, :2])
        d = float(np.linalg.norm(point - mouth) / fh)
        if best is None or d < best[0]:
            best = (d, point)
    if best is None:
        return None, None
    d, hand = best
    center = (1.0 - HAND_W) * mouth + HAND_W * hand
    center = center + np.array([0.0, DOWN_FH * fh])
    side = float(max(SIDE_FH * fh, SIDE_DIST * np.linalg.norm(mouth - hand)))
    return d, (center, side)


def crop_input(gray128: np.ndarray) -> np.ndarray:
    return np.repeat((gray128.astype(np.float32) / 255.0)[None, None], 3, 1)


def square(gray: np.ndarray, center, side: float, size: int) -> np.ndarray:
    """Square crop (edge-replicated outside the image) resized to size x size, no stretch."""
    side = max(2, int(np.ceil(side)))
    x, y = int(np.floor(center[0] - side / 2)), int(np.floor(center[1] - side / 2))
    hh, ww = gray.shape
    pad = [max(0, -y), max(0, y + side - hh), max(0, -x), max(0, x + side - ww)]
    g = cv2.copyMakeBorder(gray, *pad, cv2.BORDER_REPLICATE)
    patch = g[y + pad[0]:y + pad[0] + side, x + pad[2]:x + pad[2] + side]
    return cv2.resize(patch, (size, size), interpolation=cv2.INTER_AREA)


class HeldLive:
    def __init__(self, folder: Path, pose_weights: str = "models/yolo26n_pose_320_ncnn_model"):
        folder = Path(folder)
        sel = json.loads((folder / "held_params.json").read_text())
        self.fit = json.loads((folder / "mouth_fit.json").read_text())
        self.model = cv2.dnn.readNetFromONNX(str(folder / "held_food3.onnx"))
        self.phone_veto = bool(sel.get("phone_veto", True))
        # IR product params live in held_params.json; do not keep the SynDD 0.95 hardcoded.
        self.p_object = float((sel.get("params") or {}).get("p", P_OBJECT_DEFAULT))
        # One pose thread: the camera already runs face mesh + phone classifiers.
        self.pose = PoseEstimator(PoseConfig(weights=pose_weights, num_threads=1))
        self.kp = None
        self.last_pose = -1e9
        self.last_mesh = None
        self.hand = None  # (center, side) of the mouth-hand square, for drawing
        self.near = False
        self.window: deque = deque(maxlen=WIN)  # has_object per sample
        self.on = False
        self.kind = None
        self.state = dict(eating_drinking=False, kind=None, near=False, object=None, seen=None,
                          ms=0.0)

    def _mouth(self, t, lm, kp):
        if lm is not None:
            mouth, fh = (lm[13] + lm[14]) / 2, float(np.linalg.norm(lm[10] - lm[152]))
            self.last_mesh = (t, mouth, fh)
            return mouth, fh
        if self.last_mesh is not None and t - self.last_mesh[0] <= 1:
            return self.last_mesh[1], self.last_mesh[2]
        if kp is not None:
            got = pose_mouth(kp, self.fit)
            if got is not None:
                return got
        return None, None

    def _classify(self, gray) -> tuple[float, float]:
        """(P(cup / bottle), P(food)) for the mouth-hand crop; classes cup_bottle, empty_hand, food."""
        self.model.setInput(crop_input(square_cover(gray, *self.hand)))
        p = self.model.forward().reshape(-1)
        return float(p[0]), float(p[2])

    def feed(self, t: float, gray: np.ndarray, lm, pitch, phone_on: bool) -> dict:
        """gray: driver view; lm: face mesh (N, 2) in view pixels or None; pitch: unused;
        phone_on: the v2 call / texting alert is on."""
        if t - self.last_pose < POSE_DT:
            return dict(self.state, onsets=[])
        t0 = time.perf_counter()
        self.last_pose = t
        face_c = None if lm is None else (lm[10] + lm[152]) / 2
        person = driver_person(self.pose.detect(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)), face_c)
        self.kp = person.kpts if person is not None else None
        mouth, fh = self._mouth(t, lm, self.kp)
        near, self.hand = False, None
        if mouth is not None and self.kp is not None and fh and fh > 1:
            d, crop = grip_crop(self.kp, mouth, fh)
            near = d is not None and d <= K
            self.hand = crop
        near = near and not (self.phone_veto and phone_on)
        obj, has, seen = None, False, None
        if near:
            p_cup, p_food = self._classify(gray)
            # Cup + food mass = "something in hand"; IR product alert is drinking only.
            has = (p_cup + p_food) >= self.p_object
            obj = round(p_cup + p_food, 2)
            if has:
                seen = "drink"
        self.window.append(has)
        hits = sum(self.window)
        onsets = []
        if not self.on and hits >= ON_N:
            self.on = True
            self.kind = "drinking"
            onsets.append(self.kind)
        elif self.on and hits <= OFF_N:
            self.on, self.kind = False, None
        self.near = near
        self.state = dict(eating_drinking=self.on, kind=self.kind, near=bool(near), object=obj,
                          seen=seen if near else None,
                          ms=round((time.perf_counter() - t0) * 1000, 1))
        return dict(self.state, onsets=onsets)

    def draw(self, frame: np.ndarray) -> None:
        """Wrists, the mouth-hand square (red on alert, white when the hand is at the mouth)."""
        if self.kp is not None:
            for w in (9, 10):
                if self.kp[w, 2] >= 0.3:
                    cv2.circle(frame, (int(self.kp[w, 0]), int(self.kp[w, 1])), 7, (0, 200, 255), -1)
        if self.hand is not None:
            c, s = self.hand
            colour = (0, 0, 255) if self.on else ((255, 255, 255) if self.near else (90, 90, 90))
            cv2.rectangle(frame, (int(c[0] - s / 2), int(c[1] - s / 2)),
                          (int(c[0] + s / 2), int(c[1] + s / 2)), colour, 2)
            if self.state.get("seen"):
                cv2.putText(frame, self.state["seen"], (int(c[0] - s / 2), int(c[1] - s / 2) - 6),
                            0, 0.6, colour, 2, cv2.LINE_AA)
