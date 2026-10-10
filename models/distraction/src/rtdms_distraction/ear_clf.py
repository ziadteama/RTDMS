"""Ear-crop classifier: is there a phone at this ear? (phone / hand_no_phone / none)

A square crop beside each ear landmark (234 = driver's right, 454 = driver's left), `scale`
face widths across, pushed `outward` beyond the landmark, resized to imgsz. crop_ear() is shared
by the dataset builder (scripts/build_ear_crops.py) and the runtime, so training and inference
crop identically. The runtime smooths P(phone) per ear with an EMA.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import yaml

from .config import EarClassifierConfig, resolve_path

EARS = {"phone_right_ear": 234, "phone_left_ear": 454}
CLASSES = ("phone", "hand_no_phone", "none")


def crop_ear(img: np.ndarray, landmarks: np.ndarray, ear: int, size: int, scale: float,
             outward: float, fw: float, grayscale: bool = False) -> np.ndarray:
    """Square crop beside an ear landmark -> (size, size, 3) BGR (gray x3 if grayscale)."""
    p = landmarks[ear]
    c = 0.5 * (landmarks[234] + landmarks[454])
    u = p - c
    n = float(np.linalg.norm(u))
    u = u / n if n > 1e-6 else np.array([1.0 if ear == 454 else -1.0, 0.0])
    ctr = p + outward * fw * u
    side = max(8.0, scale * fw)
    k = size / side
    m = np.array([[k, 0, size / 2 - ctr[0] * k], [0, k, size / 2 - ctr[1] * k]], np.float64)
    out = cv2.warpAffine(img, m, (size, size), flags=cv2.INTER_AREA,
                         borderMode=cv2.BORDER_CONSTANT)
    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    if grayscale:
        out = cv2.cvtColor(cv2.cvtColor(out, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    return out


class EarClassifier:
    def __init__(self, cfg: EarClassifierConfig):
        import ncnn

        self.cfg = cfg
        d = resolve_path(cfg.weights)
        if not (d / "model.ncnn.param").is_file():
            raise FileNotFoundError(f"{d} has no NCNN model: scripts/train_ear_classifier.py")
        meta = yaml.safe_load((d / "metadata.yaml").read_text(encoding="utf8"))
        names = meta["names"]
        self.names = [names[i] for i in sorted(names)] if isinstance(names, dict) else names
        self.i_phone = self.names.index("phone")
        self._ncnn = ncnn
        self._net = ncnn.Net()
        self._net.opt.use_vulkan_compute = False
        self._net.opt.num_threads = cfg.num_threads
        self._net.load_param(str(d / "model.ncnn.param"))
        self._net.load_model(str(d / "model.ncnn.bin"))
        self._p: dict[str, float] = {}

    def probs(self, crop_bgr: np.ndarray) -> np.ndarray:
        nc = self._ncnn
        s = self.cfg.imgsz
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

    def update(self, view_bgr: np.ndarray, face, fw: float) -> dict[str, float]:
        """Smoothed P(phone) per ear behaviour for this frame."""
        c = self.cfg
        for b, ear in EARS.items():
            crop = crop_ear(view_bgr, face.landmarks, ear, c.imgsz, c.scale, c.outward, fw,
                            c.grayscale)
            p = float(self.probs(crop)[self.i_phone])
            self._p[b] = p if b not in self._p else (1 - c.ema) * self._p[b] + c.ema * p
        return dict(self._p)

    def reset(self) -> None:
        self._p.clear()


def available(cfg: EarClassifierConfig) -> bool:
    return (Path(resolve_path(cfg.weights)) / "model.ncnn.param").is_file()
