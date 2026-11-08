"""Hand boxes for the baseline (COCO has no hand class): MediaPipe Hand Landmarker.

Only the box matters to the rules, so each hand's 21 landmarks are reduced to a padded
bounding box. Once the fine-tuned detector has a `hand` class, set hands.source: detector and
this extra network drops out of the pipeline.
"""

from __future__ import annotations

import numpy as np

from .config import HandsConfig, resolve_path
from .types import Box, Detection


class MediaPipeHands:
    def __init__(self, cfg: HandsConfig):
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        path = resolve_path(cfg.model_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"{path} missing. Download:\n  curl -L -o {path} https://storage.googleapis.com/"
                "mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/"
                "hand_landmarker.task"
            )
        opts = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=cfg.num_hands,
            min_hand_detection_confidence=cfg.min_detection_confidence,
            min_hand_presence_confidence=cfg.min_detection_confidence,
            min_tracking_confidence=0.5,
        )
        self._lm = vision.HandLandmarker.create_from_options(opts)
        self.cfg = cfg
        self._last_ms = -1

    def detect(self, view_rgb: np.ndarray, t: float) -> list[Detection]:
        import mediapipe as mp

        ms = max(int(t * 1000), self._last_ms + 1)  # VIDEO mode needs strictly increasing time
        self._last_ms = ms
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(view_rgb))
        res = self._lm.detect_for_video(image, ms)
        h, w = view_rgb.shape[:2]
        out = []
        for i, hand in enumerate(res.hand_landmarks or []):
            xs = np.array([p.x for p in hand]) * w
            ys = np.array([p.y for p in hand]) * h
            bw, bh = xs.max() - xs.min(), ys.max() - ys.min()
            pad = self.cfg.pad * max(bw, bh)
            box = Box(max(0.0, xs.min() - pad), max(0.0, ys.min() - pad),
                      min(float(w), xs.max() + pad), min(float(h), ys.max() + pad))
            score = res.handedness[i][0].score if res.handedness else 1.0
            out.append(Detection("hand", float(score), box, source="mediapipe_hands"))
        return out

    def close(self) -> None:
        self._lm.close()
