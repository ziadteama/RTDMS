"""Crop classifiers on face-landmark crops (colour by default).

  ear    crops beside landmarks 234 / 454 -> phone / hand_no_phone / none
  mouth  crop centred on the lips           -> drink / food / none

crop_ear() / crop_mouth() are shared by the dataset builder (scripts/build_crops.py) and the
runtime, so training and inference crop identically. The runtime smooths each class
probability per crop with an EMA.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import yaml

from .config import EarClassifierConfig, MouthClassifierConfig, resolve_path

EARS = {"phone_right_ear": 234, "phone_left_ear": 454}
EAR_CLASSES = ("phone", "hand_no_phone", "none")
MOUTH_CLASSES = ("drink", "food", "none")
MOUTH_LANDMARKS = (13, 14, 61, 291)


def _warp(img: np.ndarray, ctr: np.ndarray, side: float, size: int, grayscale: bool):
    k = size / max(8.0, side)
    m = np.array([[k, 0, size / 2 - ctr[0] * k], [0, k, size / 2 - ctr[1] * k]], np.float64)
    out = cv2.warpAffine(img, m, (size, size), flags=cv2.INTER_AREA,
                         borderMode=cv2.BORDER_CONSTANT)
    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    if grayscale:
        out = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    return out


def ear_center(landmarks: np.ndarray, ear: int, outward: float, fw: float) -> np.ndarray:
    p = landmarks[ear]
    u = p - 0.5 * (landmarks[234] + landmarks[454])
    n = float(np.linalg.norm(u))
    u = u / n if n > 1e-6 else np.array([1.0 if ear == 454 else -1.0, 0.0])
    return p + outward * fw * u


def crop_ear(img: np.ndarray, landmarks: np.ndarray, ear: int, size: int, scale: float,
             outward: float, fw: float, grayscale: bool = False) -> np.ndarray:
    """Square crop beside an ear landmark -> (size, size, 3) BGR (gray x3 if grayscale)."""
    return _warp(img, ear_center(landmarks, ear, outward, fw), scale * fw, size, grayscale)


def mouth_center(landmarks: np.ndarray, down: float, fw: float) -> np.ndarray:
    return landmarks[list(MOUTH_LANDMARKS)].mean(axis=0) + np.array([0.0, down * fw])


def crop_mouth(img: np.ndarray, landmarks: np.ndarray, size: int, scale: float, down: float,
               fw: float, grayscale: bool = False) -> np.ndarray:
    """Square crop centred on the lips (shifted `down` fw) -> (size, size, 3) BGR."""
    return _warp(img, mouth_center(landmarks, down, fw), scale * fw, size, grayscale)


class _CropClassifier:
    def __init__(self, weights: str, imgsz: int, num_threads: int, ema: float):
        import ncnn

        d = resolve_path(weights)
        if not (d / "model.ncnn.param").is_file():
            raise FileNotFoundError(f"{d} has no NCNN model: scripts/train_crop_classifier.py")
        meta = yaml.safe_load((d / "metadata.yaml").read_text(encoding="utf8"))
        names = meta["names"]
        self.names = [names[i] for i in sorted(names)] if isinstance(names, dict) else names
        self.imgsz, self.ema = imgsz, ema
        self._ncnn = ncnn
        self._net = ncnn.Net()
        self._net.opt.use_vulkan_compute = False
        self._net.opt.num_threads = num_threads
        self._net.load_param(str(d / "model.ncnn.param"))
        self._net.load_model(str(d / "model.ncnn.bin"))
        self._p: dict[str, np.ndarray] = {}

    def probs(self, crop_bgr: np.ndarray) -> np.ndarray:
        nc = self._ncnn
        s = self.imgsz
        if crop_bgr.shape[:2] != (s, s):  # e.g. crops stored larger for a crop-size study
            crop_bgr = cv2.resize(crop_bgr, (s, s), interpolation=cv2.INTER_AREA)
        mat = nc.Mat.from_pixels(np.ascontiguousarray(crop_bgr), nc.Mat.PixelType.PIXEL_BGR2RGB,
                                 s, s)
        mat.substract_mean_normalize([], [1 / 255.0] * 3)
        ex = self._net.create_extractor()
        ex.input("in0", mat)
        _, out = ex.extract("out0")
        p = np.array(out, dtype=np.float32).reshape(-1)
        if p.min() < 0 or abs(float(p.sum()) - 1) > 1e-3:  # logits -> softmax
            e = np.exp(p - p.max())
            p = e / e.sum()
        return p

    def _smooth(self, key: str, p: np.ndarray) -> np.ndarray:
        self._p[key] = p if key not in self._p else (1 - self.ema) * self._p[key] + self.ema * p
        return self._p[key]

    def reset(self) -> None:
        self._p.clear()


class EarClassifier(_CropClassifier):
    def __init__(self, cfg: EarClassifierConfig):
        super().__init__(cfg.weights, cfg.imgsz, cfg.num_threads, cfg.ema)
        self.cfg = cfg
        self.i_phone = self.names.index("phone")

    def update(self, view_bgr: np.ndarray, face, fw: float) -> dict[str, float]:
        """Smoothed P(phone) per ear behaviour for this frame."""
        c = self.cfg
        out = {}
        for b, ear in EARS.items():
            crop = crop_ear(view_bgr, face.landmarks, ear, c.imgsz, c.scale, c.outward, fw,
                            c.grayscale)
            out[b] = float(self._smooth(b, self.probs(crop))[self.i_phone])
        return out


class MouthClassifier(_CropClassifier):
    def __init__(self, cfg: MouthClassifierConfig):
        super().__init__(cfg.weights, cfg.imgsz, cfg.num_threads, cfg.ema)
        self.cfg = cfg

    def update(self, view_bgr: np.ndarray, face, fw: float) -> dict[str, float]:
        """Smoothed {class: probability} for the mouth crop."""
        c = self.cfg
        crop = crop_mouth(view_bgr, face.landmarks, c.imgsz, c.scale, c.down, fw, c.grayscale)
        p = self._smooth("mouth", self.probs(crop))
        return {n: float(p[i]) for i, n in enumerate(self.names)}


def available(weights: str) -> bool:
    return (Path(resolve_path(weights)) / "model.ncnn.param").is_file()
