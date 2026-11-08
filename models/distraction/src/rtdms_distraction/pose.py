"""Body pose (YOLO26n-pose, NCNN) for "hand at ear" evidence.

MediaPipe Hands misses a flat hand pressed against the head and seen from the side. The wrist
and elbow keypoints of a body-pose model are found from the arm, not the hand's appearance, so
they still work there. Runs on the driver view at a small size (320) every few frames.

COCO keypoints used: 5/6 shoulders, 7/8 elbows, 9/10 wrists (person's left / right).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import PoseConfig, resolve_path
from .detector import letterbox
from .types import Box

L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW, L_WRIST, R_WRIST = 5, 6, 7, 8, 9, 10
ARMS = ((L_SHOULDER, L_ELBOW, L_WRIST), (R_SHOULDER, R_ELBOW, R_WRIST))


@dataclass
class Person:
    box: Box
    score: float
    kpts: np.ndarray  # (17, 3): x, y (driver-view pixels), visibility 0..1


def decode_pose(out: np.ndarray, conf_min: float, iou: float, nk: int = 17) -> list[tuple]:
    """Raw (5 + 3*nk) x anchors pose head -> [(box_xyxy, score, kpts (nk, 3))] in input pixels.
    Ultralytics' export already decodes boxes (cx, cy, w, h), sigmoid scores and keypoints."""
    a = np.asarray(out, dtype=np.float32)
    a = a.reshape(a.shape[-2], a.shape[-1]) if a.ndim == 3 else a
    if a.shape[0] != 5 + 3 * nk:
        a = a.T
    score = a[4]
    keep = score >= conf_min
    if not keep.any():
        return []
    a = a[:, keep]
    cx, cy, w, h = a[0], a[1], a[2], a[3]
    xywh = np.stack([cx - w / 2, cy - h / 2, w, h], 1)
    idx = np.array(cv2.dnn.NMSBoxes(xywh.tolist(), a[4].tolist(), conf_min, iou)).reshape(-1)
    out_list = []
    for i in idx:
        k = a[5:, i].reshape(nk, 3)
        out_list.append(((cx[i] - w[i] / 2, cy[i] - h[i] / 2, cx[i] + w[i] / 2, cy[i] + h[i] / 2),
                         float(a[4, i]), k.copy()))
    return out_list


class PoseEstimator:
    def __init__(self, cfg: PoseConfig):
        import ncnn

        self.cfg = cfg
        d = resolve_path(cfg.weights)
        param = d / "model.ncnn.param"
        if not param.is_file():
            raise FileNotFoundError(f"{param} missing: scripts/export_ncnn.py --weights "
                                    "models/yolo26n-pose.pt --name yolo26n_pose_320 --imgsz 320")
        self._ncnn = ncnn
        self._net = ncnn.Net()
        self._net.opt.use_vulkan_compute = False
        self._net.opt.num_threads = cfg.num_threads
        self._net.load_param(str(param))
        self._net.load_model(str(d / "model.ncnn.bin"))

    def _infer(self, img: np.ndarray) -> np.ndarray:
        nc = self._ncnn
        h, w = img.shape[:2]
        mat = nc.Mat.from_pixels(img, nc.Mat.PixelType.PIXEL_BGR2RGB, w, h)
        mat.substract_mean_normalize([], [1 / 255.0] * 3)
        ex = self._net.create_extractor()
        ex.input("in0", mat)
        _, out = ex.extract("out0")
        return np.array(out)

    def detect(self, view_bgr: np.ndarray) -> list[Person]:
        """view: driver view, BGR (or gray x3)."""
        lb, r, px, py = letterbox(view_bgr, self.cfg.imgsz)
        people = []
        for (x1, y1, x2, y2), s, k in decode_pose(self._infer(lb), self.cfg.conf, 0.5):
            # clipped to the view like Ultralytics (off-image joints otherwise differ, e.g.
            # ankles below the frame)
            k[:, 0] = np.clip((k[:, 0] - px) / r, 0, view_bgr.shape[1])
            k[:, 1] = np.clip((k[:, 1] - py) / r, 0, view_bgr.shape[0])
            people.append(Person(Box((x1 - px) / r, (y1 - py) / r, (x2 - px) / r, (y2 - py) / r),
                                 s, k))
        return people


def driver_person(people: list[Person], face_center: np.ndarray | None) -> Person | None:
    """The person whose box contains the face; else the highest-scoring one."""
    if not people:
        return None
    if face_center is not None:
        fx, fy = face_center
        inside = [p for p in people if p.box.x1 <= fx <= p.box.x2 and p.box.y1 <= fy <= p.box.y2]
        if inside:
            return max(inside, key=lambda p: p.score)
    return max(people, key=lambda p: p.score)
