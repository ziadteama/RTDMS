"""Face mesh on the driver view -> FaceObservation (head pose, gaze, mouth, jaw).

Backends produce raw landmarks; FaceAnalyzer turns them into the few numbers the rules use.

    mediapipe  MediaPipe Tasks Face Landmarker with blendshapes + transformation matrix.
    dms_face   The face subsystem's own landmarker (models/face), e.g. its LiteRT backend on the
               Pi. It does not produce blendshapes, so gaze falls back to iris geometry and jaw
               movement to the chin-nose distance.

The .task bundle is shared with models/face (no second copy of the weights).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .config import FaceMeshConfig, resolve_path
from .types import FaceObservation

# Rigid landmarks for solvePnP, from MediaPipe's canonical_face_model.obj (cm, Y up, Z out of
# the face). Mouth/jaw points are excluded: they move independently of the skull.
_CANONICAL = {
    1: (0.000000, -1.126865, 7.475604),
    4: (0.000000, -0.463170, 7.586580),
    6: (0.000000, 2.473255, 5.788627),
    33: (-4.445859, 2.663991, 3.173422),
    133: (-1.856432, 2.585245, 3.757904),
    362: (1.856432, 2.585245, 3.757904),
    263: (4.445859, 2.663991, 3.173422),
    234: (-7.664182, 0.673132, -2.435867),
    454: (7.664182, 0.673132, -2.435867),
}
POSE_IDS = tuple(_CANONICAL)
# OpenCV camera convention (Y down, Z into the scene) = 180 deg about X: (x, -y, -z).
POSE_MODEL = np.array([(x, -y, -z) for x, y, z in _CANONICAL.values()], dtype=np.float64)


@dataclass
class RawFace:
    pixels: np.ndarray  # (N, 2)
    blendshapes: dict[str, float]
    matrix: np.ndarray | None  # 4x4 canonical -> camera (OpenGL axes), MediaPipe only


class MediaPipeFaceMesh:
    def __init__(self, cfg: FaceMeshConfig, width: int, height: int):
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        path = resolve_path(cfg.model_path)
        if not path.is_file():
            raise FileNotFoundError(f"face landmarker bundle not found: {path}")
        opts = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=cfg.min_face_detection_confidence,
            min_face_presence_confidence=cfg.min_face_presence_confidence,
            min_tracking_confidence=cfg.min_tracking_confidence,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._lm = vision.FaceLandmarker.create_from_options(opts)
        self.w, self.h = width, height
        self._last_ms = -1

    def process(self, view_rgb: np.ndarray, t: float) -> RawFace | None:
        import mediapipe as mp

        ms = max(int(t * 1000), self._last_ms + 1)
        self._last_ms = ms
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(view_rgb))
        res = self._lm.detect_for_video(image, ms)
        if not res.face_landmarks:
            return None
        lms = res.face_landmarks[0]
        px = np.array([(p.x * self.w, p.y * self.h) for p in lms], dtype=np.float64)
        shapes = {c.category_name: float(c.score) for c in res.face_blendshapes[0]} \
            if res.face_blendshapes else {}
        mats = res.facial_transformation_matrixes
        matrix = np.asarray(mats[0], dtype=np.float64) if mats else None
        return RawFace(px, shapes, matrix)

    def close(self) -> None:
        self._lm.close()


class DmsFaceMesh:
    """Adapter over models/face's landmarker (installed as the `dms-face` package)."""

    def __init__(self, cfg: FaceMeshConfig, width: int, height: int):
        from dms_face.config import LandmarkerConfig

        lcfg = LandmarkerConfig(
            model_path=str(resolve_path(cfg.model_path)),
            backend=cfg.dms_face_backend,
            min_face_detection_confidence=cfg.min_face_detection_confidence,
            min_face_presence_confidence=cfg.min_face_presence_confidence,
            min_tracking_confidence=cfg.min_tracking_confidence,
            output_facial_transformation_matrixes=True,
            output_face_blendshapes=True,
        )
        if cfg.dms_face_backend == "litert":
            from dms_face.landmarker_litert import LiteRTFaceLandmarker

            self._lm = LiteRTFaceLandmarker(lcfg, width, height)
        else:
            from dms_face.landmarker import FaceLandmarkerWrapper

            self._lm = FaceLandmarkerWrapper(lcfg, width, height)

    def process(self, view_rgb: np.ndarray, t: float) -> RawFace | None:
        f = self._lm.process(np.ascontiguousarray(view_rgb), t)
        if f is None:
            return None
        shapes = {c.category_name: float(c.score) for c in f.blendshapes} if f.blendshapes else {}
        m = getattr(f.transform_matrix, "data", f.transform_matrix)
        matrix = np.asarray(m, dtype=np.float64).reshape(4, 4) if m is not None else None
        return RawFace(np.asarray(f.pixels, dtype=np.float64), shapes, matrix)

    def close(self) -> None:
        self._lm.close()


# --------------------------------------------------------------------------- geometry


def pose_from_mediapipe_matrix(m: np.ndarray) -> tuple[float, float]:
    """(pitch_down, yaw_right) degrees from MediaPipe's canonical->camera matrix.

    MediaPipe's metric space is OpenGL-like (X right, Y up, Z toward the viewer) and the
    canonical face looks along +Z. Head down rotates the face's +Z toward -Y; turning toward
    image-right rotates it toward +X.
    """
    r = m[:3, :3]
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    yaw = math.degrees(math.atan2(-r[2, 0], math.hypot(r[2, 1], r[2, 2])))
    return pitch, yaw


def pose_from_opencv_rotation(r: np.ndarray) -> tuple[float, float]:
    """(pitch_down, yaw_right) degrees from a solvePnP rotation of POSE_MODEL (OpenCV axes)."""
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    yaw = math.degrees(math.atan2(r[2, 0], math.hypot(r[2, 1], r[2, 2])))
    return pitch, yaw


class FaceAnalyzer:
    """Raw landmarks -> FaceObservation. Stateless apart from the solvePnP warm start."""

    def __init__(self, intrinsics: np.ndarray):
        self.K = np.asarray(intrinsics, dtype=np.float64)
        self._rvec: np.ndarray | None = None
        self._tvec: np.ndarray | None = None

    def solve_pose(self, px: np.ndarray) -> tuple[float, float] | None:
        img = px[list(POSE_IDS)].astype(np.float64)
        dist = np.zeros(4)
        if self._rvec is not None:  # warm start: cheap iterative refinement
            ok, rvec, tvec = cv2.solvePnP(POSE_MODEL, img, self.K, dist, self._rvec.copy(),
                                          self._tvec.copy(), True, cv2.SOLVEPNP_ITERATIVE)
        else:
            # Cold start: SQPnP is globally optimal. Unseeded ITERATIVE was measured converging to
            # the mirrored solution behind the camera on a real grayscale face.
            ok, rvec, tvec = cv2.solvePnP(POSE_MODEL, img, self.K, dist,
                                          flags=cv2.SOLVEPNP_SQPNP)
        if not ok or tvec[2, 0] <= 0:  # behind the camera = flipped solution
            self._rvec = self._tvec = None
            return None
        self._rvec, self._tvec = rvec, tvec
        return pose_from_opencv_rotation(cv2.Rodrigues(rvec)[0])

    def analyze(self, raw: RawFace) -> FaceObservation:
        px = raw.pixels
        bs = raw.blendshapes

        pose = pose_from_mediapipe_matrix(raw.matrix) if raw.matrix is not None \
            else self.solve_pose(px)
        pitch, yaw = pose if pose else (None, None)

        if "eyeLookDownLeft" in bs:
            gaze = 0.5 * (bs["eyeLookDownLeft"] + bs["eyeLookDownRight"]) \
                - 0.5 * (bs.get("eyeLookUpLeft", 0.0) + bs.get("eyeLookUpRight", 0.0))
            gaze_src = "blendshape"
        elif len(px) >= 478:
            gaze, gaze_src = iris_down_ratio(px), "iris"
        else:
            gaze, gaze_src = None, "none"

        fw = float(np.linalg.norm(px[454] - px[234]))
        if "jawOpen" in bs:
            jaw, jaw_src = bs["jawOpen"], "blendshape"
        else:
            jaw = float(np.linalg.norm(px[152] - px[1])) / fw if fw > 0 else None
            jaw_src = "geometric"

        mouth_w = float(np.linalg.norm(px[291] - px[61]))
        lip = float(np.linalg.norm(px[14] - px[13])) / mouth_w if mouth_w > 0 else 0.0

        return FaceObservation(
            landmarks=px, pitch_deg=pitch, yaw_deg=yaw, gaze_down=gaze, gaze_source=gaze_src,
            jaw_open=jaw, jaw_source=jaw_src, lip_ratio=lip, blendshapes=bs,
        )


def iris_down_ratio(px: np.ndarray) -> float:
    """Iris centre below the eye-corner line, in eye widths, averaged over both eyes."""
    vals = []
    for iris, a, b in ((468, 33, 133), (473, 263, 362)):
        mid = 0.5 * (px[a] + px[b])
        width = float(np.linalg.norm(px[a] - px[b]))
        if width > 0:
            vals.append((px[iris][1] - mid[1]) / width)
    return float(np.mean(vals)) if vals else 0.0


class FaceCropper:
    """Chooses the square region of the driver view that the face mesh sees.

    At a mirror-mounted 160-degree camera the driver's face is only ~100 px wide in the driver
    view; MediaPipe's face detector works at 128x128, so on the whole view the face shrinks to
    ~20 px and is missed. Instead:

      search  cycle through overlapping square tiles of the search region (side = search_tile x
              view size), one tile per frame, until a face is found;
      track   follow the face with a square crop of crop_scale x its size.

    Every crop is resized to crop_size. In track mode the crop moves only when the face drifts
    or resizes noticeably (hysteresis), so MediaPipe's detect-then-track sees a steady image.
    """

    def __init__(self, cfg: FaceMeshConfig, view_w: int, view_h: int):
        self.cfg = cfg
        self.view_w, self.view_h = view_w, view_h
        self.tiles = self._tiles()
        self._k = 0
        self.tracking = False
        self.box = self.tiles[0]
        self._misses = 0

    def _tiles(self) -> list[tuple[float, float, float]]:
        x, y, w, h = self.cfg.search_region
        x0, y0, w, h = x * self.view_w, y * self.view_h, w * self.view_w, h * self.view_h
        side = min(self.cfg.search_tile * max(self.view_w, self.view_h), w, h) or max(w, h)

        def starts(lo, span):
            n = max(1, math.ceil((span - side) / (side / 2)) + 1)
            return [lo + (span - side) * i / max(1, n - 1) for i in range(n)]

        return [(tx, ty, side) for ty in starts(y0, h) for tx in starts(x0, w)]

    def crop(self, view: np.ndarray) -> tuple[np.ndarray, float, float, float]:
        """-> (crop resized to crop_size, x0, y0, scale) where view = x0 + crop_px / scale."""
        if not self.tracking:
            self.box = self.tiles[self._k % len(self.tiles)]
            self._k += 1
        x0, y0, side = self.box
        n = self.cfg.crop_size
        scale = n / side
        # Affine crop handles boxes that run off the view edge (filled black).
        m = np.array([[scale, 0, -x0 * scale], [0, scale, -y0 * scale]], dtype=np.float64)
        out = cv2.warpAffine(view, m, (n, n), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT)
        return out, x0, y0, scale

    def update(self, landmarks: np.ndarray | None) -> None:
        if landmarks is None:
            self._misses += 1
            if self.tracking and self._misses >= self.cfg.lost_reset_frames:
                self.tracking = False
            return
        self._misses = 0
        lo, hi = landmarks.min(0), landmarks.max(0)
        cx, cy = (lo + hi) / 2
        want = min(float(max(hi - lo)) * self.cfg.crop_scale, float(max(self.view_w, self.view_h)))
        x0, y0, side = self.box
        drift = math.hypot(cx - (x0 + side / 2), cy - (y0 + side / 2)) / side
        if not self.tracking or drift > 0.12 or abs(want / side - 1) > 0.25:
            self.box = (cx - want / 2, cy - want / 2, want)
        self.tracking = True


class FaceMesh:
    """Cropper + backend + analyzer behind one call. Landmarks come back in view pixels."""

    def __init__(self, cfg: FaceMeshConfig, width: int, height: int, intrinsics: np.ndarray):
        backends = {"mediapipe": MediaPipeFaceMesh, "dms_face": DmsFaceMesh}
        if cfg.backend not in backends:
            raise ValueError(f"facemesh.backend must be one of {sorted(backends)}")
        self.backend = backends[cfg.backend](cfg, cfg.crop_size, cfg.crop_size)
        self.cropper = FaceCropper(cfg, width, height)
        self.analyzer = FaceAnalyzer(intrinsics)

    def process(self, view_rgb: np.ndarray, t: float) -> FaceObservation | None:
        crop, x0, y0, scale = self.cropper.crop(view_rgb)
        raw = self.backend.process(crop, t)
        if raw is None:
            self.cropper.update(None)
            return None
        raw.pixels = raw.pixels / scale + (x0, y0)
        # The transformation matrix assumes MediaPipe's own camera on the crop; rotation is
        # unaffected by the crop's translation/scale to first order, so it is kept for pose.
        self.cropper.update(raw.pixels)
        return self.analyzer.analyze(raw)

    @property
    def crop_box(self) -> tuple[float, float, float]:
        return self.cropper.box

    def close(self) -> None:
        self.backend.close()
