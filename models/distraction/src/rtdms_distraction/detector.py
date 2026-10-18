"""Object detector: YOLO26n on the rectified driver view -> phone / drink / food / hand boxes.

Backends:
    ncnn         Pi runtime (`ncnn` wheel only; no PyTorch).
    onnx         onnxruntime, same decode as ncnn.
    ultralytics  .pt weights through Ultralytics; PC / training env only.

YOLO26 exports either the end-to-end head (N x 6: x1 y1 x2 y2 score class, NMS-free) or the raw
one-to-many head ((4 + nc) x anchors, needs NMS). decode_output() accepts both, so the runtime
does not depend on which head a given export kept.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import yaml

from .config import DetectorConfig, resolve_path
from .types import Box, Detection

PAD_VALUE = 114


def letterbox(img: np.ndarray, size: int) -> tuple[np.ndarray, float, float, float]:
    """Resize keeping aspect, pad to size x size (centred, like Ultralytics export).
    Returns (image, scale, pad_x, pad_y)."""
    h, w = img.shape[:2]
    r = min(size / w, size / h)
    nw, nh = round(w * r), round(h * r)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR) if (nw, nh) != (w, h) \
        else img
    px, py = (size - nw) / 2, (size - nh) / 2
    top, left = round(py - 0.1), round(px - 0.1)
    out = cv2.copyMakeBorder(resized, top, size - nh - top, left, size - nw - left,
                             cv2.BORDER_CONSTANT, value=(PAD_VALUE,) * 3)
    return out, r, left, top


def decode_output(
    out: np.ndarray, num_classes: int, conf_min: float, iou: float, nms: bool = True,
    max_det: int = 300,
) -> list[tuple[float, float, float, float, float, int]]:
    """Network output -> [(x1, y1, x2, y2, score, class_id)] in letterboxed-input pixels.

    nms=False is for a raw export of YOLO26's ONE-TO-ONE head (scripts/export_ncnn.py
    --head one2one): it was trained to emit one box per object, so threshold + top-k replaces
    NMS, exactly as Ultralytics' end-to-end post-processing does (per-anchor best class here).
    """
    a = np.asarray(out, dtype=np.float32)
    a = a.reshape(a.shape[-2], a.shape[-1]) if a.ndim == 3 else a
    if a.ndim != 2:
        raise ValueError(f"unexpected detector output shape {np.shape(out)}")

    # End-to-end head: one row per box (max_det rows, 300 by default). Raw heads have thousands
    # of anchors, which is what separates the two when 4 + nc happens to equal 6.
    if a.shape[1] == 6 and (4 + num_classes != 6 or a.shape[0] <= 1000):
        keep = a[:, 4] >= conf_min
        return [(float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), int(r[5]))
                for r in a[keep]]

    if a.shape[0] != 4 + num_classes:  # raw head stored anchors-first
        a = a.T
    if a.shape[0] != 4 + num_classes:
        raise ValueError(f"output {np.shape(out)} does not match {num_classes} classes")
    scores = a[4:]
    cls = scores.argmax(0)
    conf = scores[cls, np.arange(scores.shape[1])]
    keep = conf >= conf_min
    if not keep.any():
        return []
    cx, cy, w, h = a[0, keep], a[1, keep], a[2, keep], a[3, keep]
    conf, cls = conf[keep], cls[keep]
    if nms:
        boxes_xywh = np.stack([cx - w / 2, cy - h / 2, w, h], 1)
        idx = cv2.dnn.NMSBoxesBatched(boxes_xywh.tolist(), conf.tolist(), cls.tolist(), conf_min,
                                      iou)
        idx = np.array(idx).reshape(-1)
    else:
        idx = np.argsort(-conf)[:max_det]
    return [(float(cx[i] - w[i] / 2), float(cy[i] - h[i] / 2), float(cx[i] + w[i] / 2),
             float(cy[i] + h[i] / 2), float(conf[i]), int(cls[i])) for i in idx]


def load_metadata(weights: Path) -> dict:
    """Ultralytics export metadata.yaml (NCNN folder, or next to an ONNX file), else {}."""
    m = weights / "metadata.yaml" if weights.is_dir() else weights.with_suffix(".metadata.yaml")
    return yaml.safe_load(m.read_text(encoding="utf8")) if m.is_file() else {}


def load_class_names(weights: Path) -> list[str]:
    """Class names shipped with an export: Ultralytics metadata.yaml, or <stem>.names.json."""
    candidates = [weights / "metadata.yaml"] if weights.is_dir() else [
        weights.with_suffix(".names.json"), weights.parent / "metadata.yaml"]
    for c in candidates:
        if c.is_file():
            if c.suffix == ".json":
                return list(json.loads(c.read_text(encoding="utf8")))
            names = yaml.safe_load(c.read_text(encoding="utf8"))["names"]
            return [names[i] for i in sorted(names)] if isinstance(names, dict) else list(names)
    raise FileNotFoundError(f"no class names found next to {weights}")


class Detector:
    """Common front end: letterbox, run backend, decode, map classes, undo letterbox."""

    def __init__(self, cfg: DetectorConfig):
        self.cfg = cfg
        self.weights = resolve_path(cfg.weights)
        self.names: list[str] = []
        # model class id -> our class; built once the backend knows the model's names
        self._map: dict[int, str] = {}
        self._min_conf = min(cfg.conf.values()) if cfg.conf else 0.25
        # export_ncnn.py --head one2one tags the export; such a model must NOT get NMS.
        meta = load_metadata(self.weights) if self.weights.exists() else {}
        self.head = meta.get("rtdms_head", "one2many")

    def _set_names(self, names: list[str]) -> None:
        self.names = names
        cmap = self.cfg.class_map
        self._map = {i: cmap[n] for i, n in enumerate(names) if n in cmap}
        if not self._map:
            raise ValueError(f"class_map matches none of the model's classes: {names[:10]}...")

    def set_conf(self, value: float) -> None:
        """One threshold for every class (live tuning)."""
        self.cfg.conf = dict.fromkeys(self.cfg.conf or {"phone": 0, "drink": 0, "food": 0,
                                                         "hand": 0}, value)
        self._min_conf = value

    def _infer(self, img: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def detect(self, view: np.ndarray) -> list[Detection]:
        """view: (H, W, 3) uint8 in OpenCV BGR order, as Ultralytics expects for numpy input.
        The pipeline feeds grayscale x3, where channel order does not matter."""
        lb, r, px, py = letterbox(view, self.cfg.imgsz)
        raw = decode_output(self._infer(lb), len(self.names), self._min_conf, self.cfg.nms_iou,
                            nms=self.head != "one2one")
        return self._finish(raw, r, px, py, view.shape[1], view.shape[0])

    def _finish(self, raw, r, px, py, w, h) -> list[Detection]:
        dets = []
        for x1, y1, x2, y2, score, cid in raw:
            cls = self._map.get(cid)
            if cls is None or score < self.cfg.conf.get(cls, self._min_conf):
                continue
            box = Box(max(0.0, (x1 - px) / r), max(0.0, (y1 - py) / r),
                      min(float(w), (x2 - px) / r), min(float(h), (y2 - py) / r))
            if box.area > 0:
                dets.append(Detection(cls, score, box))
        return dets


class NcnnDetector(Detector):
    def __init__(self, cfg: DetectorConfig):
        super().__init__(cfg)
        import ncnn

        d = self.weights
        param, binf = d / "model.ncnn.param", d / "model.ncnn.bin"
        if not param.is_file():
            raise FileNotFoundError(f"{param} missing; run scripts/export_ncnn.py")
        self._ncnn = ncnn
        self._net = ncnn.Net()
        self._net.opt.use_vulkan_compute = False
        self._net.opt.num_threads = cfg.num_threads
        self._net.load_param(str(param))
        self._net.load_model(str(binf))
        self._set_names(load_class_names(d))

    def _infer(self, img: np.ndarray) -> np.ndarray:
        nc = self._ncnn
        h, w = img.shape[:2]
        # Grayscale replicated to 3 channels, so BGR vs RGB order is irrelevant here.
        mat = nc.Mat.from_pixels(img, nc.Mat.PixelType.PIXEL_BGR2RGB, w, h)
        mat.substract_mean_normalize([], [1 / 255.0] * 3)
        ex = self._net.create_extractor()
        ex.input("in0", mat)
        _, out = ex.extract("out0")
        return np.array(out)


class OnnxDetector(Detector):
    def __init__(self, cfg: DetectorConfig):
        super().__init__(cfg)
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = cfg.num_threads
        so.inter_op_num_threads = 1
        self._sess = ort.InferenceSession(str(self.weights), so,
                                          providers=["CPUExecutionProvider"])
        self._input = self._sess.get_inputs()[0].name
        meta = self._sess.get_modelmeta().custom_metadata_map
        if "names" in meta:  # Ultralytics stores a dict literal here
            names = yaml.safe_load(meta["names"])
            self._set_names([names[i] for i in sorted(names)])
        else:
            self._set_names(load_class_names(self.weights))

    def _infer(self, img: np.ndarray) -> np.ndarray:
        x = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        return self._sess.run(None, {self._input: np.ascontiguousarray(x)})[0]


class UltralyticsDetector(Detector):
    """PC-only convenience; uses Ultralytics' own pre/post-processing.

    rect=False forces the fixed square letterbox the NCNN/ONNX exports see; Ultralytics' default
    for .pt is a minimal rectangle, which changes confidences by up to ~0.14 (EVIDENCE.md).
    """

    def __init__(self, cfg: DetectorConfig):
        super().__init__(cfg)
        from ultralytics import YOLO

        self._model = YOLO(str(self.weights))
        names = self._model.names
        self._set_names([names[i] for i in sorted(names)])

    def detect(self, view: np.ndarray) -> list[Detection]:
        res = self._model.predict(view, imgsz=self.cfg.imgsz, conf=self._min_conf,
                                  iou=self.cfg.nms_iou, rect=False, verbose=False)[0]
        b = res.boxes
        raw = [(*xyxy, float(c), int(k)) for xyxy, c, k in
               zip(b.xyxy.cpu().numpy().tolist(), b.conf.cpu().numpy(), b.cls.cpu().numpy(),
                   strict=True)]
        return self._finish(raw, 1.0, 0.0, 0.0, view.shape[1], view.shape[0])


def make_detector(cfg: DetectorConfig) -> Detector:
    backends = {"ncnn": NcnnDetector, "onnx": OnnxDetector, "ultralytics": UltralyticsDetector}
    if cfg.backend not in backends:
        raise ValueError(f"detector.backend must be one of {sorted(backends)}")
    return backends[cfg.backend](cfg)
