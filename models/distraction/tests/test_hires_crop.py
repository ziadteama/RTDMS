"""facemesh.hires_crop: the face crop is cut from the full-resolution frame at the same place."""

import cv2
import numpy as np

from rtdms_distraction.config import FaceMeshConfig
from rtdms_distraction.facemesh import FaceCropper
from rtdms_distraction.roi import DriverROI


def frame_with_marks(w=1296, h=972):
    rng = np.random.default_rng(0)
    f = cv2.GaussianBlur(rng.integers(0, 255, (h, w), np.uint8), (0, 0), 3)
    cv2.circle(f, (300, 250), 40, 255, -1)  # a bright "face" at known frame pixels
    return f


def test_view_to_frame_maps_view_pixels_back_to_the_frame():
    roi = DriverROI(1296, 972, None, 640, 640)
    ox, oy, k = roi.view_to_frame()
    assert (ox, oy) == (0.0, 0.0) and abs(k - 1296 / 640) < 1e-9
    roi = DriverROI(1296, 972, [100, 50, 648, 486], 640, 640)
    ox, oy, k = roi.view_to_frame()
    assert (ox, oy) == (100.0, 50.0) and abs(k - 648 / 640) < 1e-9


def test_no_mapping_when_masked():
    roi = DriverROI(1296, 972, None, 640, 640, mask_polygons=[[[0, 0], [0.1, 0], [0.1, 0.1]]])
    assert roi.view_to_frame() is None


def test_hires_crop_shows_the_same_region_with_the_same_coordinates():
    frame = frame_with_marks()
    roi = DriverROI(1296, 972, None, 640, 640)
    view = cv2.cvtColor(roi.apply(frame), cv2.COLOR_GRAY2RGB)
    cfg = FaceMeshConfig()
    a, b = FaceCropper(cfg, roi.out_w, roi.out_h), FaceCropper(cfg, roi.out_w, roi.out_h)
    a.tracking = b.tracking = True
    a.box = b.box = (100.0, 80.0, 90.0)  # view px: square around the circle at (148, 123)
    lo, *coords_lo = a.crop(view)
    hi, *coords_hi = b.crop(view, frame, roi.view_to_frame())
    assert coords_lo == coords_hi  # landmarks map back to view pixels the same way
    assert hi.shape == lo.shape == (cfg.crop_size, cfg.crop_size, 3)
    corr = np.corrcoef(lo[..., 0].ravel().astype(float), hi[..., 0].ravel().astype(float))[0, 1]
    assert corr > 0.9  # same picture
    # sharper: the full-resolution crop keeps more detail than the upscaled view crop
    assert cv2.Laplacian(hi[..., 0], cv2.CV_64F).var() > cv2.Laplacian(lo[..., 0], cv2.CV_64F).var()
