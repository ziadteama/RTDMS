"""Fisheye intrinsics (cv2.fisheye, equidistant model): checkerboard calibration, load, save.

The 160-degree lens is far outside what the pinhole + radial model in cv2.calibrateCamera can
represent; cv2.fisheye's 4-coefficient model is the one built for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import yaml


@dataclass
class FisheyeCalibration:
    K: np.ndarray  # (3, 3)
    D: np.ndarray  # (4, 1)
    width: int
    height: int
    rms: float | None = None
    n_images: int | None = None

    def scaled_to(self, width: int, height: int) -> FisheyeCalibration:
        """Same lens at another resolution of the SAME field of view (e.g. binned vs full).

        Refuses an aspect-ratio change: on OV5647 that means a different sensor crop, which
        moves the optical centre and invalidates K.
        """
        if (width, height) == (self.width, self.height):
            return self
        sx, sy = width / self.width, height / self.height
        if abs(sx - sy) > 1e-3:
            raise ValueError(
                f"calibration is {self.width}x{self.height}; {width}x{height} has a different "
                "aspect ratio (different sensor crop). Recalibrate at this resolution."
            )
        K = self.K.copy()
        K[0, :] *= sx
        K[1, :] *= sy
        return FisheyeCalibration(K, self.D.copy(), width, height, self.rms, self.n_images)

    def save(self, path: str | Path) -> None:
        data = {
            "model": "opencv_fisheye_equidistant",
            "image_width": self.width,
            "image_height": self.height,
            "K": self.K.tolist(),
            "D": self.D.reshape(-1).tolist(),
            "rms_px": self.rms,
            "n_images": self.n_images,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

    @classmethod
    def load(cls, path: str | Path) -> FisheyeCalibration:
        with open(path, encoding="utf8") as f:
            d = yaml.safe_load(f)
        return cls(
            K=np.array(d["K"], dtype=np.float64),
            D=np.array(d["D"], dtype=np.float64).reshape(4, 1),
            width=int(d["image_width"]),
            height=int(d["image_height"]),
            rms=d.get("rms_px"),
            n_images=d.get("n_images"),
        )


def find_corners(gray: np.ndarray, pattern: tuple[int, int]) -> np.ndarray | None:
    """Inner-corner grid (cols, rows) -> (N, 1, 2) float32 sub-pixel corners, or None."""
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    ok, corners = cv2.findChessboardCorners(gray, pattern, flags)
    if not ok:
        return None
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01)
    return cv2.cornerSubPix(gray, corners, (5, 5), (-1, -1), crit)


def _flag(name: str) -> int:
    """cv2.fisheye.CALIB_* in OpenCV 4; moved to cv2.CALIB_* in OpenCV 5."""
    v = getattr(cv2.fisheye, f"CALIB_{name}", None)
    return int(v if v is not None else getattr(cv2, f"CALIB_{name}"))


def calibrate(
    corner_sets: list[np.ndarray],
    pattern: tuple[int, int],
    square_size: float,
    image_size: tuple[int, int],
) -> FisheyeCalibration:
    """Run cv2.fisheye.calibrate over corner sets from find_corners()."""
    cols, rows = pattern
    objp = np.zeros((1, cols * rows, 3), np.float64)
    objp[0, :, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_size
    obj = [objp] * len(corner_sets)
    img = [c.reshape(1, -1, 2).astype(np.float64) for c in corner_sets]
    K = np.zeros((3, 3))
    D = np.zeros((4, 1))
    flags = _flag("RECOMPUTE_EXTRINSIC") | _flag("CHECK_COND") | _flag("FIX_SKEW")
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6)
    rms, K, D, _, _ = cv2.fisheye.calibrate(obj, img, image_size, K, D, None, None, flags, crit)
    return FisheyeCalibration(K, D, image_size[0], image_size[1], float(rms), len(corner_sets))
