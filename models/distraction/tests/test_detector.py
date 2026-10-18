import numpy as np
import pytest

from rtdms_distraction.config import DetectorConfig
from rtdms_distraction.detector import Detector, decode_output, letterbox

NAMES = ["person", "cell phone", "cup", "banana"]


def test_letterbox_geometry():
    img = np.zeros((640, 480, 3), np.uint8)  # portrait
    out, r, px, py = letterbox(img, 416)
    assert out.shape == (416, 416, 3)
    assert r == pytest.approx(416 / 640)
    assert py == 0 and px == pytest.approx((416 - 312) / 2, abs=1)
    assert out[0, 0, 0] == 114  # padding value


def raw_head(boxes, nc=4, anchors=3549):
    """(4 + nc, anchors) raw output with the given (cx, cy, w, h, cls, score) in the first rows."""
    a = np.zeros((4 + nc, anchors), np.float32)
    for i, (cx, cy, w, h, c, s) in enumerate(boxes):
        a[:4, i] = (cx, cy, w, h)
        a[4 + c, i] = s
    return a


def test_decode_raw_head_with_nms():
    a = raw_head([(100, 100, 40, 80, 1, 0.9), (102, 101, 40, 80, 1, 0.7),
                  (300, 300, 50, 50, 2, 0.6)])
    out = decode_output(a[None], len(NAMES), 0.25, 0.5)
    assert len(out) == 2  # duplicate phone suppressed
    phone = max(out, key=lambda r: r[4])
    assert phone[5] == 1 and phone[:4] == pytest.approx((80, 60, 120, 140))
    # anchors-first layout decodes the same
    assert len(decode_output(a.T, len(NAMES), 0.25, 0.5)) == 2


def test_decode_end_to_end_head():
    e2e = np.zeros((300, 6), np.float32)
    e2e[0] = (10, 20, 50, 90, 0.8, 1)
    e2e[1] = (0, 0, 5, 5, 0.1, 2)
    out = decode_output(e2e[None], len(NAMES), 0.25, 0.5)
    assert out == [(10.0, 20.0, 50.0, 90.0, pytest.approx(0.8), 1)]


class FakeDetector(Detector):
    def __init__(self, cfg, output):
        super().__init__(cfg)
        self._set_names(NAMES)
        self._out = output

    def _infer(self, img):
        return self._out


def test_class_map_thresholds_and_letterbox_undo():
    cfg = DetectorConfig(class_map={"cell phone": "phone", "cup": "drink"},
                         conf={"phone": 0.3, "drink": 0.65})
    # View 640x480 -> r = 0.65, pad y = (416 - 312) / 2 = 52
    a = raw_head([(208, 52 + 65, 26, 52, 1, 0.9),    # phone
                  (100, 200, 30, 30, 2, 0.5),        # cup below its 0.65 threshold
                  (300, 200, 30, 30, 0, 0.99)])      # person: not mapped
    d = FakeDetector(cfg, a[None])
    dets = d.detect(np.zeros((480, 640, 3), np.uint8))
    assert [x.cls for x in dets] == ["phone"]
    b = dets[0].box
    assert (b.cx, b.cy, b.w, b.h) == pytest.approx((320, 100, 40, 80), abs=0.6)


def test_class_map_must_match_model():
    with pytest.raises(ValueError):
        FakeDetector(DetectorConfig(class_map={"phone": "phone"}), None)
