"""Driver region of interest: fisheye rectification of the driver's part of the frame only.

Fully undistorting a 160-degree image to one pinhole view stretches the edges enormously, and
the driver sits near an edge. Instead this builds a *virtual pinhole camera* aimed at the centre
of the driver ROI, with a focal length chosen so the ROI just fills the output. The result is a
low-distortion view of the driver, computed with one cv2.remap over precomputed maps (only the
output pixels are touched, never the full frame).

Every later stage (detector, face mesh, rules, overlay) works in this rectified view, and its
intrinsics are known exactly, which also makes solvePnP head pose metric instead of guessed.

With rectification disabled (non-fisheye sources) the ROI is a plain crop scaled to fit.
"""

from __future__ import annotations

import cv2
import numpy as np

from .calibration import FisheyeCalibration

MAX_RAY_ANGLE_DEG = 85.0


def _boundary_points(x: float, y: float, w: float, h: float, n: int = 24) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n)
    top = np.stack([x + t * w, np.full(n, y)], 1)
    bottom = np.stack([x + t * w, np.full(n, y + h)], 1)
    left = np.stack([np.full(n, x), y + t * h], 1)
    right = np.stack([np.full(n, x + w), y + t * h], 1)
    return np.concatenate([top, bottom, left, right]).astype(np.float64)


def _rays(points: np.ndarray, K: np.ndarray, D: np.ndarray) -> np.ndarray:
    """Raw fisheye pixels -> unit rays in the camera frame (X right, Y down, Z forward)."""
    norm = cv2.fisheye.undistortPoints(points.reshape(1, -1, 2), K, D).reshape(-1, 2)
    rays = np.concatenate([norm, np.ones((len(norm), 1))], 1)
    return rays / np.linalg.norm(rays, axis=1, keepdims=True)


def virtual_camera(
    calib: FisheyeCalibration, rect: list[float], out_w: int, out_h: int
) -> tuple[np.ndarray, np.ndarray]:
    """Rotation R (camera -> virtual) and intrinsics P of a pinhole view covering `rect`."""
    x, y, w, h = (float(v) for v in rect)
    centre = _rays(np.array([[x + w / 2, y + h / 2]]), calib.K, calib.D)[0]
    edge = _rays(_boundary_points(x, y, w, h), calib.K, calib.D)
    if np.degrees(np.arccos(np.clip(edge[:, 2], -1, 1))).max() > MAX_RAY_ANGLE_DEG:
        raise ValueError(
            f"ROI {rect} reaches more than {MAX_RAY_ANGLE_DEG} deg off-axis; a pinhole view "
            "cannot hold it. Draw a tighter ROI."
        )

    z = centre
    xa = np.cross([0.0, 1.0, 0.0], z)  # keep the virtual camera's horizon level
    xa /= np.linalg.norm(xa)
    ya = np.cross(z, xa)
    R = np.stack([xa, ya, z])

    v = edge @ R.T
    u, w_ = v[:, 0] / v[:, 2], v[:, 1] / v[:, 2]
    span_u, span_v = u.max() - u.min(), w_.max() - w_.min()
    f = min(out_w / span_u, out_h / span_v)
    cx = -u.min() * f + (out_w - f * span_u) / 2
    cy = -w_.min() * f + (out_h - f * span_v) / 2
    P = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]], dtype=np.float64)
    return R, P


class DriverROI:
    """Raw grayscale frame -> rectified (or cropped) driver view, plus coordinate mapping."""

    def __init__(
        self,
        frame_w: int,
        frame_h: int,
        rect: list[int] | None,
        out_w: int,
        out_h: int,
        calib: FisheyeCalibration | None = None,
        mask_polygons: list[list[list[float]]] | None = None,
    ):
        self.frame_w, self.frame_h = frame_w, frame_h
        self.rect = list(rect) if rect else [0, 0, frame_w, frame_h]
        x, y, w, h = self.rect
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > frame_w or y + h > frame_h:
            raise ValueError(f"ROI {self.rect} does not fit a {frame_w}x{frame_h} frame")

        self.calib = calib.scaled_to(frame_w, frame_h) if calib is not None else None
        if self.calib is not None:
            self.R, self.P = virtual_camera(self.calib, self.rect, out_w, out_h)
            self.out_w, self.out_h = out_w, out_h
            self._map1, self._map2 = cv2.fisheye.initUndistortRectifyMap(
                self.calib.K, self.calib.D, self.R, self.P, (out_w, out_h), cv2.CV_16SC2
            )
        else:
            # Plain crop, scaled to fit the output box with the aspect ratio kept.
            self.scale = min(out_w / w, out_h / h)
            self.out_w, self.out_h = round(w * self.scale), round(h * self.scale)
            # No calibration: the usual focal ~= frame width guess. Absolute pitch is then
            # biased, but every head-pose rule is relative to the driver's baseline.
            f = frame_w * self.scale
            self.P = np.array(
                [[f, 0, (frame_w / 2 - x) * self.scale], [0, f, (frame_h / 2 - y) * self.scale],
                 [0, 0, 1]],
                dtype=np.float64,
            )

        self._mask = None
        if mask_polygons:
            keep = np.full((self.out_h, self.out_w), 255, np.uint8)
            for poly in mask_polygons:
                pts = np.array(poly, np.float64) * [self.out_w, self.out_h]
                cv2.fillPoly(keep, [pts.round().astype(np.int32)], 0)
            self._mask = keep == 0

    @property
    def rectified(self) -> bool:
        return self.calib is not None

    @property
    def intrinsics(self) -> np.ndarray:
        return self.P

    def apply(self, gray: np.ndarray) -> np.ndarray:
        """(H, W) uint8 raw frame -> (out_h, out_w) uint8 driver view."""
        if self.calib is not None:
            out = cv2.remap(gray, self._map1, self._map2, cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT)
        else:
            x, y, w, h = self.rect
            crop = gray[y:y + h, x:x + w]
            out = crop if self.scale == 1.0 else cv2.resize(
                crop, (self.out_w, self.out_h), interpolation=cv2.INTER_AREA
            )
            if self._mask is not None:
                out = out.copy()
        if self._mask is not None:
            out[self._mask] = 0
        return out

    def to_raw(self, pts: np.ndarray) -> np.ndarray:
        """(N, 2) driver-view pixels -> raw frame pixels."""
        pts = np.asarray(pts, np.float64).reshape(-1, 2)
        if self.calib is None:
            return pts / self.scale + self.rect[:2]
        h = np.concatenate([pts, np.ones((len(pts), 1))], 1)
        rays = (np.linalg.inv(self.P) @ h.T).T @ self.R  # back into the real camera frame
        rays = rays.reshape(-1, 1, 3)
        raw, _ = cv2.fisheye.projectPoints(rays, np.zeros(3), np.zeros(3), self.calib.K,
                                           self.calib.D)
        return raw.reshape(-1, 2)

    def from_raw(self, pts: np.ndarray) -> np.ndarray:
        """(N, 2) raw frame pixels -> driver-view pixels."""
        pts = np.asarray(pts, np.float64).reshape(-1, 2)
        if self.calib is None:
            return (pts - self.rect[:2]) * self.scale
        v = _rays(pts, self.calib.K, self.calib.D) @ self.R.T
        uv = v[:, :2] / v[:, 2:3]
        return uv * [self.P[0, 0], self.P[1, 1]] + [self.P[0, 2], self.P[1, 2]]
