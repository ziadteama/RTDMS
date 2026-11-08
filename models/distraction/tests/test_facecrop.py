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


# --------------------------------------------------------------------------- driver lock


class SceneBackend:
    """Fake landmarker: returns the FIRST listed face whose centre is inside the current crop
    (like num_faces=1 picking someone else), in crop pixels."""

    def __init__(self, mesh, faces):
        self.mesh, self.faces = mesh, faces  # faces: list of (cx, cy, size)

    def process(self, crop, t):
        from rtdms_distraction.facemesh import RawFace

        x0, y0, side = self.mesh.cropper.box
        k = crop.shape[0] / side
        for cx, cy, size in self.faces:
            if x0 <= cx <= x0 + side and y0 <= cy <= y0 + side:
                return RawFace((face_pts(cx, cy, size) - (x0, y0)) * k, {}, None)
        return None


def locked_mesh(faces, **kw):
    from types import SimpleNamespace

    from rtdms_distraction.facemesh import DriverLock, FaceMesh

    cfg = FaceMeshConfig(**kw)
    m = FaceMesh.__new__(FaceMesh)  # no model files: fake backend + identity analyzer
    m.cropper = FaceCropper(cfg, 640, 640)
    m.analyzer = SimpleNamespace(analyze=lambda raw: raw.pixels)
    x, y, w, h = cfg.search_region
    m.lock = DriverLock((x * 640, y * 640, (x + w) * 640, (y + h) * 640), cfg.relock_after_s,
                        cfg.lock_max_jump, cfg.lock_max_scale)
    m._tiles_seen = 0
    m.backend = SceneBackend(m, faces)
    return m


def run(m, t0, t1, fps=30):
    out, t = [], t0
    while t < t1:
        out.append((t, m.process(np.zeros((640, 640, 3), np.uint8), t)))
        t += 1 / fps
    return out


def test_driver_lock_takes_the_largest_face_and_ignores_others():
    # someone behind (small, listed first so the landmarker would pick them) + the driver
    faces = [(560, 200, 60), (320, 250, 120)]
    m = locked_mesh(faces)
    out = run(m, 0.0, 1.0)
    assert m.lock.locked and abs(m.lock.size - 120) < 1e-6
    got = [px for _, px in out if px is not None]
    assert got and all(abs(face_size_of(px) - 120) < 1e-6 for px in got)
    # the other person leans into the driver's crop: ignored, the lock stays on the driver
    faces[0] = (400, 250, 60)
    out = run(m, 1.0, 1.5)
    assert all(px is None for _, px in out) and m.lock.locked
    assert np.allclose(m.lock.center, (320, 250))


def test_driver_lock_reacquires_only_after_one_second_lost():
    faces = [(320, 250, 120)]
    m = locked_mesh(faces)
    run(m, 0.0, 1.0)
    assert m.lock.locked
    faces.clear()  # driver gone (e.g. turned away)
    run(m, 1.0, 1.9)
    assert m.lock.locked  # < 1 s: still locked, crop stays on the driver
    run(m, 1.9, 2.2)
    assert not m.lock.locked  # > 1 s: released, searching
    faces.append((250, 260, 110))
    out = run(m, 2.2, 3.5)
    assert m.lock.locked and any(px is not None for _, px in out)


def face_size_of(px):
    return float(max(px.max(0) - px.min(0)))
