import numpy as np

from rtdms_distraction.config import FaceMeshConfig
from rtdms_distraction.facemesh import FaceCropper


def face_pts(cx, cy, size):
    return np.array([[cx - size / 2, cy - size / 2], [cx + size / 2, cy + size / 2]])


def test_search_tiles_cover_region_and_cycle():
    c = FaceCropper(FaceMeshConfig(search_region=[0, 0, 1, 0.7], search_tile=0.45), 640, 640)
    xs = [t[0] for t in c.tiles] + [t[0] + t[2] for t in c.tiles]
    ys = [t[1] for t in c.tiles] + [t[1] + t[2] for t in c.tiles]
    assert min(xs) == 0 and max(xs) == 640 and min(ys) == 0 and max(ys) == 448
    seen = set()
    for _ in range(len(c.tiles)):
        c.crop(np.zeros((640, 640, 3), np.uint8))
        seen.add(c.box)
    assert len(seen) == len(c.tiles)


def test_tracking_hysteresis_and_reset():
    cfg = FaceMeshConfig(crop_scale=2.0, lost_reset_frames=3)
    c = FaceCropper(cfg, 640, 640)
    c.update(face_pts(300, 200, 100))
    assert c.tracking and c.box == (200, 100, 200)
    c.update(face_pts(305, 203, 102))  # small drift: crop stays put
    assert c.box == (200, 100, 200)
    c.update(face_pts(360, 200, 100))  # 30 % of the crop: re-centre
    assert c.box[0] == 260
    crop, x0, y0, scale = c.crop(np.zeros((640, 640, 3), np.uint8))
    assert crop.shape == (cfg.crop_size, cfg.crop_size, 3) and scale == cfg.crop_size / 200
    for _ in range(3):
        c.update(None)
    assert not c.tracking


def test_crop_maps_back_to_view_pixels():
    c = FaceCropper(FaceMeshConfig(crop_size=256), 640, 640)
    c.update(face_pts(400, 300, 80))
    view = np.zeros((640, 640, 3), np.uint8)
    view[300, 400] = 255
    crop, x0, y0, scale = c.crop(view)
    ys, xs = np.nonzero(crop[:, :, 0])
    back = np.array([xs.mean(), ys.mean()]) / scale + (x0, y0)
    assert np.abs(back - (400, 300)).max() < 1.0
