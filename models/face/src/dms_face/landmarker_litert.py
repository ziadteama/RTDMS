"""
LiteRT (TFLite runtime) backend for the Face Landmarker -- no MediaPipe needed.

Runs the two networks packed inside `face_landmarker.task` (it is a zip):

    face_detector.tflite            BlazeFace short-range, 128x128
    face_landmarks_detector.tflite  478 points (468 mesh + 10 iris), 256x256

and reproduces the parts of MediaPipe's VIDEO-mode graph that the downstream
arithmetic depends on:

  - detect-then-track: the detector only runs when there is no tracked face;
    otherwise the previous frame's landmarks define this frame's crop
  - rotated square ROI, 1.5x the face box, aligned to the eye line
  - the same One Euro landmark smoothing MediaPipe applies with num_faces=1
    (min_cutoff 0.05, beta 80, derivative cutoff 1.0, scaled by face size)

Why bother: MediaPipe drags in a large framework and pins its own threads.
`ai-edge-litert` is the bare runtime with XNNPACK, so on a Pi 5 the mesh costs
a few milliseconds on ONE thread, leaving the other cores for phone, physiology
and fusion.

Facial transformation matrix and blendshapes are not produced (both are
optional in LandmarkFrame and nothing downstream requires them).
"""

import math
import os
import time
import zipfile

import cv2
import numpy as np

from . import landmark_ids as L
from .landmarker import LandmarkFrame
from .paths import resolve_under_package

DET_SIZE = 128
MESH_SIZE = 256
ROI_SCALE = 1.5

# Index of the eye keypoints in BlazeFace's 6-keypoint output.
_DET_RIGHT_EYE, _DET_LEFT_EYE = 0, 1


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(-100.0, min(100.0, float(x)))))


def _ssd_anchors():
    """BlazeFace short-range anchors: 16x16x2 + 8x8x6 = 896, centres only
    (fixed_anchor_size, so width/height are 1 and drop out of the decode)."""
    strides = [8, 16, 16, 16]
    anchors, layer = [], 0
    while layer < len(strides):
        last, per_cell = layer, 0
        while last < len(strides) and strides[last] == strides[layer]:
            per_cell += 2  # aspect ratio 1.0 + the interpolated scale
            last += 1
        fm = math.ceil(DET_SIZE / strides[layer])
        for y in range(fm):
            for x in range(fm):
                anchors += [((x + 0.5) / fm, (y + 0.5) / fm)] * per_cell
        layer = last
    return np.array(anchors, np.float32)


class _OneEuro:
    """Vectorised port of MediaPipe's OneEuroFilter (one_euro_filter.cc)."""

    def __init__(self, min_cutoff=0.05, beta=80.0, d_cutoff=1.0, frequency=30.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.frequency = frequency
        self.reset()

    def reset(self):
        self._x = None  # filtered value
        self._raw = None  # last raw value
        self._dx = None  # filtered derivative
        self._t = None

    def _alpha(self, cutoff):
        te = 1.0 / self.frequency
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / te)

    def __call__(self, value, t, value_scale):
        if self._t is not None:
            if t <= self._t:
                return self._x
            self.frequency = 1.0 / (t - self._t)
        self._t = t
        if self._raw is None:
            dvalue = np.zeros_like(value)
        else:
            dvalue = (value - self._raw) * value_scale * self.frequency
        self._raw = value
        a_d = self._alpha(self.d_cutoff)
        self._dx = dvalue if self._dx is None else a_d * dvalue + (1 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * np.abs(self._dx)
        te = 1.0 / self.frequency
        a = 1.0 / (1.0 + (1.0 / (2.0 * np.pi * cutoff)) / te)
        self._x = value if self._x is None else a * value + (1 - a) * self._x
        return self._x


class LiteRTFaceLandmarker:
    """Drop-in for FaceLandmarkerWrapper: same constructor and process()."""

    def __init__(self, cfg, width, height, running_mode="video"):
        from ai_edge_litert.interpreter import Interpreter

        task_path = str(resolve_under_package(cfg.model_path))
        if not os.path.isfile(task_path):
            raise FileNotFoundError(f"model bundle not found: {task_path}")
        with zipfile.ZipFile(task_path) as z:
            det_bytes = z.read("face_detector.tflite")
            mesh_bytes = z.read("face_landmarks_detector.tflite")

        threads = getattr(cfg, "num_threads", 1)
        self._det = self._load(Interpreter, det_bytes, threads)
        self._mesh = self._load(Interpreter, mesh_bytes, threads)
        mesh_out = self._mesh.get_output_details()
        self._mesh_lm = next(d["index"] for d in mesh_out if d["shape"][-1] == 478 * 3)
        # Two scalar heads; the face-presence logit is the 4-D [1,1,1,1] one.
        self._mesh_flag = next(d["index"] for d in mesh_out if len(d["shape"]) == 4
                               and d["shape"][-1] == 1)
        det_out = self._det.get_output_details()
        self._det_reg = next(d["index"] for d in det_out if d["shape"][-1] == 16)
        self._det_cls = next(d["index"] for d in det_out if d["shape"][-1] == 1)

        self.cfg = cfg
        self.width, self.height = width, height
        self._tracking = running_mode == "video"
        self._anchors = _ssd_anchors()
        self._roi = None
        self._smoother = _OneEuro()
        self.iris_available = None

        # Per-frame timings, for the HUD / benchmarks.
        self.last_detector_ms = 0.0
        self.last_mesh_ms = 0.0
        self.detector_runs = 0

    @staticmethod
    def _load(Interpreter, model_bytes, threads):
        it = Interpreter(model_content=model_bytes, num_threads=threads)
        it.allocate_tensors()
        return it

    @staticmethod
    def _invoke(it, x):
        it.set_tensor(it.get_input_details()[0]["index"], x)
        it.invoke()

    # -- detector -----------------------------------------------------------
    def _detect(self, rgb):
        """Best face as an ROI (center, size, angle) in pixels, or None."""
        h, w = rgb.shape[:2]
        side = max(w, h)
        pad_x, pad_y = (side - w) // 2, (side - h) // 2
        sq = cv2.copyMakeBorder(rgb, pad_y, side - h - pad_y, pad_x, side - w - pad_x,
                                cv2.BORDER_CONSTANT)
        x = cv2.resize(sq, (DET_SIZE, DET_SIZE), interpolation=cv2.INTER_AREA)
        x = (x.astype(np.float32) * (2.0 / 255.0) - 1.0)[None]
        self._invoke(self._det, x)
        reg = self._det.get_tensor(self._det_reg)[0]
        scores = self._det.get_tensor(self._det_cls)[0, :, 0]
        best = int(np.argmax(scores))
        if _sigmoid(scores[best]) < self.cfg.min_face_detection_confidence:
            return None
        r = reg[best] / DET_SIZE
        ax, ay = self._anchors[best]

        def px(nx, ny):
            return np.array([nx * side - pad_x, ny * side - pad_y], np.float64)

        center = px(r[0] + ax, r[1] + ay)
        size = max(r[2], r[3]) * side * ROI_SCALE
        k = 4 + 2 * _DET_RIGHT_EYE, 4 + 2 * _DET_LEFT_EYE
        eye_r = px(r[k[0]] + ax, r[k[0] + 1] + ay)
        eye_l = px(r[k[1]] + ax, r[k[1] + 1] + ay)
        angle = math.atan2(eye_l[1] - eye_r[1], eye_l[0] - eye_r[0])
        return center, size, angle

    # -- mesh ---------------------------------------------------------------
    def _mesh_on(self, rgb, roi):
        """(478x3 pixel landmarks, presence probability) for this ROI."""
        center, size, angle = roi
        m = cv2.getRotationMatrix2D((float(center[0]), float(center[1])),
                                    math.degrees(angle), MESH_SIZE / size)
        m[0, 2] += MESH_SIZE / 2 - center[0]
        m[1, 2] += MESH_SIZE / 2 - center[1]
        crop = cv2.warpAffine(rgb, m, (MESH_SIZE, MESH_SIZE), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT)
        self._invoke(self._mesh, (crop.astype(np.float32) * (1.0 / 255.0))[None])
        lm = self._mesh.get_tensor(self._mesh_lm).reshape(-1, 3).astype(np.float64)
        presence = _sigmoid(self._mesh.get_tensor(self._mesh_flag).ravel()[0])
        inv = cv2.invertAffineTransform(m)
        pts = lm.copy()
        pts[:, :2] = lm[:, :2] @ inv[:, :2].T + inv[:, 2]
        pts[:, 2] *= size / MESH_SIZE
        return pts, presence

    @staticmethod
    def _roi_from_landmarks(pts):
        """Square crop aligned with the eye line (outer eye corners)."""
        a, b = pts[L.RIGHT_EYE_CORNER_OUTER], pts[L.LEFT_EYE_CORNER_OUTER]
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        c, s = math.cos(angle), math.sin(angle)
        xa = pts[:, 0] * c + pts[:, 1] * s
        ya = -pts[:, 0] * s + pts[:, 1] * c
        cxa, cya = (xa.min() + xa.max()) / 2, (ya.min() + ya.max()) / 2
        size = max(xa.max() - xa.min(), ya.max() - ya.min()) * ROI_SCALE
        center = np.array([cxa * c - cya * s, cxa * s + cya * c])
        return center, size, angle

    # -- public -------------------------------------------------------------
    def process(self, frame_rgb, timestamp_s):
        """Run one frame. Returns a LandmarkFrame, or None if no face."""
        self.last_detector_ms = 0.0
        roi = self._roi if self._tracking else None
        if roi is None:
            t = time.perf_counter()
            roi = self._detect(frame_rgb)
            self.last_detector_ms = (time.perf_counter() - t) * 1000.0
            self.detector_runs += 1
            self._smoother.reset()
            if roi is None:
                self._roi = None
                self.last_mesh_ms = 0.0
                return None

        t = time.perf_counter()
        pts, presence = self._mesh_on(frame_rgb, roi)
        self.last_mesh_ms = (time.perf_counter() - t) * 1000.0
        if presence < self.cfg.min_face_presence_confidence:
            self._roi = None
            self._smoother.reset()
            return None
        # Next frame's crop comes from the raw landmarks, as in MediaPipe;
        # smoothing is for the consumers, not the tracker.
        self._roi = self._roi_from_landmarks(pts)

        xy = pts[:, :2]
        span = xy.max(axis=0) - xy.min(axis=0)
        object_scale = max(1e-6, float(span.mean()))
        smoothed = self._smoother(pts, timestamp_s, 1.0 / object_scale)

        has_iris = len(smoothed) >= L.N_LANDMARKS_WITH_IRIS
        if self.iris_available is None:
            self.iris_available = has_iris
        return LandmarkFrame(
            landmarks=None,
            pixels=np.ascontiguousarray(smoothed[:, :2]),
            has_iris=has_iris,
            transform_matrix=None,
            blendshapes=None,
        )

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
