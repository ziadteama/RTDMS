import numpy as np
import pytest

from rtdms_distraction.domain import (
    barrel,
    clip_boxes,
    convert,
    head_shoulders_crop,
    ir_look,
    occlude,
)


def scene(w=800, h=600):
    img = np.full((h, w, 3), 90, np.uint8)
    box = (0, 520.0, 300.0, 600.0, 420.0)  # a "phone" off-centre, toward the right
    img[300:420, 520:600] = 230
    return img, [box]


def mask_bbox(img):
    ys, xs = np.nonzero(img[:, :, 0] > 160)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


@pytest.mark.parametrize("seed", range(5))
def test_barrel_moves_boxes_with_the_pixels(seed):
    img, boxes = scene()
    out, nb = barrel(img, boxes, np.random.default_rng(seed), fov_deg=100)
    assert len(nb) == 1
    x1, y1, x2, y2 = mask_bbox(out)
    _, bx1, by1, bx2, by2 = nb[0]
    assert abs(bx1 - x1) < 3 and abs(by1 - y1) < 3 and abs(bx2 - x2) < 3 and abs(by2 - y2) < 3


def test_barrel_actually_bends_lines():
    img = np.full((600, 800, 3), 0, np.uint8)
    img[290:310, :] = 255  # horizontal bar away from the optical axis
    rng = np.random.default_rng(1)
    out, _ = barrel(img, [], rng, fov_deg=110)
    cols = [c for c in range(0, 800, 40) if out[:, c, 0].max() > 128]
    rows = [np.nonzero(out[:, c, 0] > 128)[0].mean() for c in cols]
    assert np.ptp(rows) > 5  # no longer a straight horizontal line


def test_crop_keeps_objects_and_face():
    img, boxes = scene(1600, 1200)
    faces = [(0.30, 0.10, 0.38, 0.22)]  # normalised face box above-left of the phone
    crop, nb = head_shoulders_crop(img, [(0, 1040.0, 600.0, 1200.0, 840.0)], faces,
                                   np.random.default_rng(0))
    h, w = crop.shape[:2]
    assert abs(h - w) <= 1  # square, like the driver ROI
    assert len(nb) == 1
    c, x1, y1, x2, y2 = nb[0]
    assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h


def test_clip_drops_mostly_outside_boxes():
    assert clip_boxes([(0, -90.0, 0.0, 10.0, 50.0)], 100, 100) == []
    assert clip_boxes([(0, -5.0, 0.0, 95.0, 50.0)], 100, 100)[0][1] == 0.0


def test_ir_look_is_gray_and_same_size():
    img, _ = scene()
    out = ir_look(img, np.random.default_rng(0))
    assert out.shape == img.shape
    assert (out[:, :, 0] == out[:, :, 1]).all() and (out[:, :, 1] == out[:, :, 2]).all()


def test_occlusion_covers_part_not_all_of_the_object():
    img, boxes = scene()
    out = occlude(img, boxes, np.random.default_rng(3), p=1.0)
    patch = (out[300:420, 520:600].astype(int) - img[300:420, 520:600]).any(axis=2)
    assert 0.05 < patch.mean() < 0.9


def test_convert_end_to_end_resizes_and_keeps_labels():
    img, boxes = scene(1280, 960)
    boxes = [(0, 832.0, 480.0, 960.0, 672.0)]
    out, nb = convert(img, boxes, [], np.random.default_rng(0), out_size=640)
    assert max(out.shape[:2]) <= 640 and len(nb) == 1


def test_color_look_keeps_colour_and_convert_defaults_to_it():
    from rtdms_distraction.domain import color_look

    img = np.zeros((200, 300, 3), np.uint8)
    img[:, :, 2] = 200  # red
    out = color_look(img, np.random.default_rng(0))
    assert out.shape == img.shape
    assert out[:, :, 2].mean() > out[:, :, 0].mean() + 50  # still red, not gray
    conv, _ = convert(img, [], [], np.random.default_rng(1), crop=False, p_barrel=0.0)
    assert conv[:, :, 2].mean() > conv[:, :, 0].mean() + 50
