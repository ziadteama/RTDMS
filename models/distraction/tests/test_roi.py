import cv2
import numpy as np
import pytest

from rtdms_distraction.calibration import FisheyeCalibration
from rtdms_distraction.roi import DriverROI

W, H = 1296, 972


def calib():
    # Equidistant lens with ~160 deg across the 1296 px width: f = 648 / radians(80) ~ 465.
    K = np.array([[465.0, 0, 652.0], [0, 465.0, 480.0], [0, 0, 1]])
    D = np.array([[0.05], [-0.02], [0.004], [-0.0005]])
    return FisheyeCalibration(K, D, W, H)


def project(pts3d, c):
    raw, _ = cv2.fisheye.projectPoints(pts3d.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), c.K, c.D)
    return raw.reshape(-1, 2)


def test_raw_view_round_trip():
    roi = DriverROI(W, H, [700, 150, 500, 650], 640, 640, calib())
    raw = np.array([[750.0, 200.0], [950.0, 475.0], [1150.0, 760.0]])
    back = roi.to_raw(roi.from_raw(raw))
    assert np.abs(back - raw).max() < 0.05


def test_roi_fills_the_view_and_centre_maps_inside():
    roi = DriverROI(W, H, [700, 150, 500, 650], 640, 640, calib())
    v = roi.from_raw(np.array([[950.0, 475.0]]))[0]
    assert 0 < v[0] < 640 and 0 < v[1] < 640
    corners = roi.from_raw(np.array([[700.0, 150], [1200, 150], [700, 800], [1200, 800]]))
    assert corners[:, 0].min() >= -1 and corners[:, 0].max() <= 641
    assert corners[:, 1].min() >= -1 and corners[:, 1].max() <= 641
    # The ROI spans the view along at least one axis (tight fit, no wasted pixels).
    span = corners.max(0) - corners.min(0)
    assert max(span[0] / 640, span[1] / 640) > 0.9


def test_rectified_view_straightens_lines():
    """A straight 3D line is curved in the fisheye image and straight in the driver view."""
    c = calib()
    t = np.linspace(-0.6, 0.6, 15)
    line = np.stack([0.9 + t * 0.3, t, np.full_like(t, 1.0)], 1)  # off-axis, toward image-right
    raw = project(line, c)
    roi = DriverROI(W, H, [800, 100, 450, 700], 640, 640, c)

    def curvature(p):
        a, b = p[0], p[-1]
        u, v = b - a, p - a
        d = (u[0] * v[:, 1] - u[1] * v[:, 0]) / np.linalg.norm(u)
        return np.abs(d).max()

    assert curvature(raw) > 5.0  # visibly bent in the raw fisheye frame
    assert curvature(roi.from_raw(raw)) < 0.5


def test_remap_matches_coordinate_mapping():
    """Pixels land where from_raw() says they do."""
    c = calib()
    roi = DriverROI(W, H, [700, 150, 500, 650], 640, 640, c)
    img = np.zeros((H, W), np.uint8)
    cv2.circle(img, (950, 475), 6, 255, -1)
    view = roi.apply(img)
    ys, xs = np.nonzero(view > 128)
    expected = roi.from_raw(np.array([[950.0, 475.0]]))[0]
    assert abs(xs.mean() - expected[0]) < 1.0 and abs(ys.mean() - expected[1]) < 1.0


def test_plain_crop_without_calibration():
    roi = DriverROI(640, 480, [320, 0, 320, 480], 640, 640)
    assert (roi.out_w, roi.out_h) == (427, 640)
    img = np.arange(480 * 640, dtype=np.uint32).reshape(480, 640).astype(np.uint8)
    assert roi.apply(img).shape == (640, 427)
    p = np.array([[400.0, 100.0]])
    assert np.allclose(roi.to_raw(roi.from_raw(p)), p)


def test_full_frame_default_and_mask():
    roi = DriverROI(200, 100, None, 200, 100, mask_polygons=[[[0, 0], [0.5, 0], [0.5, 1], [0, 1]]])
    out = roi.apply(np.full((100, 200), 200, np.uint8))
    assert out[:, :95].max() == 0 and out[:, 105:].min() == 200


def test_rejects_roi_outside_frame_and_too_wide():
    with pytest.raises(ValueError):
        DriverROI(W, H, [1000, 0, 400, 400], 640, 640)
    with pytest.raises(ValueError):
        DriverROI(W, H, [0, 0, W, H], 640, 640, calib())  # whole 160-deg frame: not a pinhole


def test_calibration_scaling(tmp_path):
    c = calib()
    half = c.scaled_to(648, 486)
    assert half.K[0, 0] == pytest.approx(232.5) and half.K[0, 2] == pytest.approx(326.0)
    with pytest.raises(ValueError):
        c.scaled_to(1920, 1080)  # different sensor crop
    p = tmp_path / "cam.yaml"
    c.save(p)
    back = FisheyeCalibration.load(p)
    assert np.allclose(back.K, c.K) and np.allclose(back.D, c.D)


def test_fisheye_calibration_recovers_synthetic_lens():
    from rtdms_distraction.calibration import calibrate

    c = calib()
    pattern, sq = (9, 6), 0.03
    obj = np.zeros((54, 3))
    obj[:, :2] = np.mgrid[0:9, 0:6].T.reshape(-1, 2) * sq
    rng = np.random.default_rng(0)
    views = []
    for _ in range(25):
        rvec = rng.uniform(-0.5, 0.5, 3)
        tvec = np.array([rng.uniform(-0.6, 0.4), rng.uniform(-0.4, 0.3), rng.uniform(0.35, 0.7)])
        img, _ = cv2.fisheye.projectPoints(obj.reshape(-1, 1, 3), rvec, tvec, c.K, c.D)
        img = img.reshape(-1, 2)
        if (img[:, 0].min() > 5 and img[:, 0].max() < W - 5 and img[:, 1].min() > 5
                and img[:, 1].max() < H - 5):
            views.append(img.reshape(-1, 1, 2).astype(np.float32))
    assert len(views) >= 12
    est = calibrate(views, pattern, sq, (W, H))
    assert est.rms < 0.01
    assert np.allclose(est.K, c.K, rtol=1e-3, atol=0.5)
