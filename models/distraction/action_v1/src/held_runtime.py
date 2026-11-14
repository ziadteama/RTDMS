"""Held-object drinking check at runtime: self-contained (numpy + cv2 + ncnn only), for the Pi.

Same geometry as the offline evaluation (held_geometry.hand_geometry / pose_mouth,
build_held.square_cover) and the same rule (held_alerts.DrinkingRule), without the training-side
imports (no D: paths, no ultralytics, no torch).

    det = HeldDrinking(model_dir, fit_json, params={"p": .95, "x": 5, "window": .3})
    out = det.feed(t, gray, face_landmarks_or_None, pose_kp_or_None, pitch_or_None)
"""

import json
from pathlib import Path

import cv2
import numpy as np
from held_alerts import DrinkingRule

CONF = 0.3
H, K = 0.35, 1.25  # loose gate (D27), used by the clean nano model


def _valid(kp, i):
    return kp is not None and bool(np.isfinite(kp[i]).all() and kp[i, 2] >= CONF)


def _stretch(img):
    lo, hi = np.percentile(img, (1, 99))
    if hi - lo < 8:
        return img
    return np.clip((img.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def pose_mouth(kp, fit):
    """Mouth + face height from COCO head points when the face mesh is lost (D26 fallback)."""
    # Same as held_geometry.head + pose_mouth.
    if kp is None or not all(_valid(kp, i) for i in (0, 1, 2)):
        return None
    nose = kp[0, :2]
    vector = nose - (kp[1, :2] + kp[2, :2]) / 2
    scales = {"inter_eye": float(np.linalg.norm(kp[1, :2] - kp[2, :2]))}
    eye_ear = [np.linalg.norm(kp[e, :2] - kp[a, :2]) for e, a in ((1, 3), (2, 4)) if _valid(kp, a)]
    scales["eye_ear"] = float(np.mean(eye_ear)) if eye_ear else float("nan")
    for name in [fit["preferred_height"]] + [s for s in scales if s != fit["preferred_height"]]:
        fh = scales[name] * fit["g"][name]
        if np.isfinite(fh) and fh > 1:
            return nose + fit["c"] * vector, float(fh)
    return None


def hand_geometry(kp, mouth, fh, h=H):
    best = None
    for elbow, wrist in ((7, 9), (8, 10)):
        if not _valid(kp, wrist):
            continue
        point = kp[wrist, :2].copy()
        if _valid(kp, elbow):
            point += h * (kp[wrist, :2] - kp[elbow, :2])
        d = float(np.linalg.norm(point - mouth) / fh)
        if best is None or d < best[0]:
            best = (d, point)
    if best is None:
        return None, None
    d, point = best
    center = (mouth + point) / 2
    side = max(2 * fh, 1.3 * np.linalg.norm(mouth - point))
    return d, (center, side)


def square_cover(gray, center, side):
    side = max(2, int(np.ceil(side)))
    x, y = int(np.floor(center[0] - side / 2)), int(np.floor(center[1] - side / 2))
    hh, ww = gray.shape
    left, top = max(0, -x), max(0, -y)
    right, bottom = max(0, x + side - ww), max(0, y + side - hh)
    padded = cv2.copyMakeBorder(gray, top, bottom, left, right, cv2.BORDER_REPLICATE)
    patch = padded[y + top:y + top + side, x + left:x + left + side]
    return _stretch(cv2.resize(patch, (128, 128), interpolation=cv2.INTER_AREA))


class CupModel:
    """NCNN classifier (FP32 or INT8 export of the held cup model); returns P(cup_bottle)."""

    def __init__(self, folder, threads=4):
        import ncnn
        import yaml

        folder = Path(folder)
        self.ncnn = ncnn
        self.net = ncnn.Net()
        self.net.opt.num_threads = threads
        self.net.opt.use_vulkan_compute = False
        assert self.net.load_param(str(folder / "model.ncnn.param")) == 0
        assert self.net.load_model(str(folder / "model.ncnn.bin")) == 0
        meta = yaml.safe_load((folder / "metadata.yaml").read_text())
        self.index = next(int(i) for i, n in meta["names"].items() if n == "cup_bottle")
        self.size = int(meta["imgsz"][0])
        self.inp, self.out = self.net.input_names()[0], self.net.output_names()[0]

    def __call__(self, gray128):
        x = cv2.resize(gray128, (self.size, self.size))
        x = np.ascontiguousarray(np.repeat((x.astype(np.float32) / 255.0)[None], 3, 0))
        ex = self.net.create_extractor()
        ex.input(self.inp, self.ncnn.Mat(x))
        _, y = ex.extract(self.out)
        return float(np.asarray(y).reshape(-1)[self.index])


class HeldDrinking:
    def __init__(self, model_dir, fit_json, params, threads=4):
        self.cup = CupModel(model_dir, threads)
        self.fit = json.loads(Path(fit_json).read_text())
        self.rule = DrinkingRule(**params)
        self.last_mesh = None

    def feed(self, t, gray, lm=None, kp=None, pitch=None, veto=False):
        """lm: face mesh (N, 2) view pixels or None; kp: COCO pose (17, 3) or None (hold the last
        one between pose runs); veto: True while the phone pipeline says call / texting."""
        mouth = fh = None
        if lm is not None:
            mouth, fh = (lm[13] + lm[14]) / 2, float(np.linalg.norm(lm[10] - lm[152]))
            self.last_mesh = (t, mouth, fh)
        elif self.last_mesh is not None and t - self.last_mesh[0] <= 1:
            _, mouth, fh = self.last_mesh
        elif kp is not None:
            got = pose_mouth(kp, self.fit)
            if got is not None:
                mouth, fh = got
        near, p = False, None
        if mouth is not None and kp is not None and fh and fh > 1:
            d, crop = hand_geometry(kp, np.asarray(mouth), fh)
            near = d is not None and d <= K and not veto
            if near:
                p = self.cup(square_cover(gray, *crop))
        on, onset = self.rule.update(t, near, p, pitch)
        return dict(drinking=on, onset=onset, near=near, cup=p)
