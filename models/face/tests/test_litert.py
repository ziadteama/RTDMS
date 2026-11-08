"""
Deterministic parts of the LiteRT landmarker backend.

The networks themselves need the runtime and a camera, so these cover the
arithmetic around them: anchor layout, ROI geometry and landmark smoothing.
None of this imports ai_edge_litert.
"""

import math

import numpy as np

from dms_face import landmark_ids as L
from dms_face.landmarker_litert import LiteRTFaceLandmarker, _OneEuro, _ssd_anchors


def test_anchor_layout_matches_blazeface_short_range():
    a = _ssd_anchors()
    assert a.shape == (896, 2)
    # 16x16 grid, 2 anchors per cell, then 8x8 grid, 6 per cell.
    assert np.allclose(a[0], [0.5 / 16, 0.5 / 16])
    assert np.allclose(a[1], a[0])
    assert np.allclose(a[511], [15.5 / 16, 15.5 / 16])
    assert np.allclose(a[512], [0.5 / 8, 0.5 / 8])
    assert np.allclose(a[-1], [7.5 / 8, 7.5 / 8])


def _face_points(angle_deg, cx=320.0, cy=240.0, half=50.0):
    """478 points on a square of side 2*half, rotated, with the outer eye
    corners on the square's top edge so the eye line has the given angle."""
    pts = np.zeros((478, 2))
    corners = np.array([[-half, -half], [half, -half], [half, half], [-half, half]])
    for i in range(478):
        pts[i] = corners[i % 4]
    pts[L.RIGHT_EYE_CORNER_OUTER] = [-half, -half]
    pts[L.LEFT_EYE_CORNER_OUTER] = [half, -half]
    t = math.radians(angle_deg)
    rot = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    return pts @ rot.T + [cx, cy]


def test_roi_from_landmarks_recovers_centre_size_and_roll():
    for angle in (0.0, 20.0, -35.0):
        center, size, roi_angle = LiteRTFaceLandmarker._roi_from_landmarks(_face_points(angle))
        assert np.allclose(center, [320.0, 240.0], atol=1e-6)
        assert math.isclose(size, 100.0 * 1.5, rel_tol=1e-6)  # face box x ROI scale
        assert math.isclose(math.degrees(roi_angle), angle, abs_tol=1e-6)


def test_one_euro_passes_a_constant_through_unchanged():
    f = _OneEuro()
    x = np.full((478, 3), 7.0)
    for i in range(30):
        out = f(x, i / 30.0, value_scale=0.01)
    assert np.allclose(out, 7.0)


def test_one_euro_smooths_jitter_but_follows_a_real_move():
    rng = np.random.default_rng(0)
    f = _OneEuro()
    scale = 1.0 / 100.0  # a 100 px face
    # Sub-pixel jitter around a fixed point is damped...
    outs = [f(np.array([100.0 + rng.normal(0, 0.3)]), i / 30.0, scale) for i in range(60)]
    assert np.std(outs[30:]) < 0.3
    # ...while a 40 px jump is tracked within a few frames (beta raises the cutoff).
    for i in range(60, 66):
        out = f(np.array([140.0]), i / 30.0, scale)
    assert abs(out[0] - 140.0) < 2.0


def test_one_euro_ignores_repeated_timestamps():
    f = _OneEuro()
    first = f(np.array([1.0]), 1.0, 1.0)
    again = f(np.array([50.0]), 1.0, 1.0)
    assert np.allclose(first, again)
