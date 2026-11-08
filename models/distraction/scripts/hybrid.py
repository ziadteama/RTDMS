"""Live v2 phone alerts (action classifier + phone checks) for stream.py --hybrid.

Per frame, from the face mesh:
  upper-body crop (2.5 x face size, 224 px)  -> action classifier (call, drinking, eating,
                                                hand_on_face, normal, other, texting)
  two ear crops (1.2 x face width, 128 px)   -> phone-in-hand classifier (ears)
  lap crop (2.5 x face size under the chin)  -> phone-in-hand classifier (lap)
  CALL    = action "call" in >= 70% of the last 2 s AND mean ear phone prob > 0.5
  TEXTING = action "texting" in >= 70% of the last 1.5 s AND mean lap phone prob > 0.4
Crops get the same 1st-99th percentile contrast stretch as in training. Models are INT8 NCNN
exports from D:/rtdms-data/action_v1 (REPORT_v2.md). The phone checks only run while the action
classifier says call / texting, so they cost nothing the rest of the time.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from hybrid_alerts import CLASSES, AlertLogic

R_EAR, L_EAR, LIP_T, LIP_B = 234, 454, 13, 14
LAP_SIDE, LAP_DOWN = 2.5, 1.25
EAR_P, LAP_P = 0.5, 0.4


def square(img, cx, cy, side):
    """Square crop centred at (cx, cy), shifted (not cut) to stay inside the image."""
    h, w = img.shape[:2]
    side = int(round(min(side, w, h)))
    x1 = int(round(min(max(cx - side / 2, 0), w - side)))
    y1 = int(round(min(max(cy - side / 2, 0), h - side)))
    return img[y1:y1 + side, x1:x1 + side], (x1, y1, side)


def stretch(img):
    lo, hi = np.percentile(img, (1, 99))
    if hi - lo < 8:
        return img
    return np.clip((img.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def crops(gray, lm):
    """lm (N, 2) view pixels -> crops + their boxes (x, y, side) for drawing + lip gap."""
    x1, y1 = lm.min(0)
    x2, y2 = lm.max(0)
    size = max(y2 - y1, x2 - x1)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    up, b_up = square(gray, cx, cy + 0.3 * size, 2.5 * size)
    fw = float(np.linalg.norm(lm[R_EAR] - lm[L_EAR])) or (x2 - x1)
    ears, b_ears = [], []
    for e, other in ((R_EAR, L_EAR), (L_EAR, R_EAR)):
        out = lm[e] - lm[other]
        out = out / (np.linalg.norm(out) or 1.0)
        c = lm[e] + out * 0.25 * fw + np.array([0, 0.1 * fw])
        im, b = square(gray, c[0], c[1], 1.2 * fw)
        ears.append(im)
        b_ears.append(b)
    lap, b_lap = square(gray, cx, y2 + LAP_DOWN * size, LAP_SIDE * size)
    lip = float(np.linalg.norm(lm[LIP_T] - lm[LIP_B]) / fw)
    return (up, ears[0], ears[1], lap), (b_up, *b_ears, b_lap), lip


class Ncnn:
    """Ultralytics classify export (softmax inside); returns probs in `order`."""

    def __init__(self, d: Path, order: list[str], threads: int = 4):
        import ncnn

        self.ncnn = ncnn
        self.net = ncnn.Net()
        self.net.opt.num_threads = threads
        self.net.opt.use_vulkan_compute = False
        self.net.load_param(str(d / "model.ncnn.param"))
        self.net.load_model(str(d / "model.ncnn.bin"))
        meta = yaml.safe_load((d / "metadata.yaml").read_text())
        names = [meta["names"][i] for i in range(len(meta["names"]))]
        self.idx = [names.index(c) for c in order]
        self.size = int(meta["imgsz"][0])
        self.inp, self.out = self.net.input_names()[0], self.net.output_names()[0]

    def __call__(self, gray: np.ndarray) -> np.ndarray:
        x = stretch(cv2.resize(gray, (self.size, self.size), interpolation=cv2.INTER_AREA))
        x = np.ascontiguousarray(np.repeat((x.astype(np.float32) / 255.0)[None], 3, 0))
        ex = self.net.create_extractor()
        ex.input(self.inp, self.ncnn.Mat(x))
        p = np.array(ex.extract(self.out)[1]).reshape(-1)
        return p[self.idx]


class Hybrid:
    def __init__(self, model_dir: str | Path, threads: int = 4):
        d = Path(model_dir)
        self.action = Ncnn(d / "action_n224_int8_ncnn_model", CLASSES, threads)
        self.ear = Ncnn(d / "phone_ear_n128_int8_ncnn_model", ["phone_in_hand"], threads)
        self.lap = Ncnn(d / "phone_lap_n128_int8_ncnn_model", ["phone_in_hand"], threads)
        self.logic = AlertLogic(alerts=("call", "texting"), use_talk=False, lap_p=LAP_P,
                                phone_p=EAR_P, min_p={"texting": 0.0})
        self.last: dict = {}
        self.boxes = None

    def feed(self, t: float, gray: np.ndarray, lm: np.ndarray | None) -> dict:
        """gray: the driver view; lm: face-mesh landmarks in view pixels (None = no face)."""
        t0 = time.perf_counter()
        if lm is None:
            self.boxes = None
            out = {"face": False, "call": False, "texting": False, "action": None, "p": None,
                   "ear": None, "lap": None, "ms": 0.0}
            self.last = out
            return out
        (up, er, el, lap), self.boxes, lip = crops(gray, np.asarray(lm, np.float64))
        probs = self.action(up)
        top = CLASSES[int(probs.argmax())]
        ear = lapp = None
        if top == "call":
            ear = float(max(self.ear(er)[0], self.ear(el)[0]))
        elif top == "texting":
            lapp = float(self.lap(lap)[0])
        state, onsets = self.logic.update(t, probs, ear, lip, lapp)
        out = {"face": True, "call": state["call"], "texting": state["texting"], "action": top,
               "p": round(float(probs.max()), 2),
               "ear": None if ear is None else round(ear, 2),
               "lap": None if lapp is None else round(lapp, 2),
               "onsets": onsets, "ms": round((time.perf_counter() - t0) * 1000, 1)}
        self.last = out
        return out

    def draw(self, view: np.ndarray, scale: float = 1.0) -> None:
        """Crop boxes on the BGR overlay (upper body grey, ears / lap coloured when used)."""
        if self.boxes is None:
            return
        s = self.last
        cols = [(110, 110, 110),
                (0, 200, 255) if s.get("ear") is not None else (80, 80, 80),
                (0, 200, 255) if s.get("ear") is not None else (80, 80, 80),
                (255, 160, 0) if s.get("lap") is not None else (80, 80, 80)]
        for (x, y, side), c in zip(self.boxes, cols, strict=True):
            p1 = (int(x * scale), int(y * scale))
            p2 = (int((x + side) * scale), int((y + side) * scale))
            cv2.rectangle(view, p1, p2, c, 1, cv2.LINE_AA)
