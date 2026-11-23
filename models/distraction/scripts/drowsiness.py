"""Drowsiness (eye closure, blinks, PERCLOS) from the face subsystem (models/face, `dms_face`),
run on the same camera frames as the distraction pipeline so one process owns the camera.

Used by scripts/stream.py --drowsiness. The face subsystem's EAR, blink state machine, PERCLOS
windows and per-driver calibration run unchanged, but on the 478 landmarks the distraction
pipeline already found (its face crop + driver lock find small, distant faces that the face
subsystem's whole-frame detector misses), so no second face network runs. Its two-phase
calibration (10 s eyes open, 3 s closed) runs per frame, as in models/face/stream.py.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

# models/distraction/scripts -> models/face/src (repo); bundle layout distraction/ + face/ too.
_FACE_SRC = Path(__file__).resolve().parents[2] / "face" / "src"
if _FACE_SRC.is_dir() and str(_FACE_SRC) not in sys.path:
    sys.path.insert(0, str(_FACE_SRC))


def parse_phone_calibration(body: bytes) -> dict:
    """Validate a request before it reaches the pipeline thread."""
    from dms_face.calibration import DriverProfile, profile_from_phone

    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError, RecursionError) as e:
        raise ValueError("invalid JSON") from e
    profile_from_phone(payload, DriverProfile())
    return payload


class Calibration:
    """models/face/stream.py's WebCalibration, trimmed: per-frame, waits for a face."""

    COUNTDOWN_S = 3.0

    def __init__(self, cfg, profile_name: str):
        from dms_face.calibration import CalibrationCollector

        self._collector_cls = CalibrationCollector
        c = cfg.calibration
        self.cfg, self.profile_name = c, profile_name
        self.phases = [("open", c.open_phase_s, "Look straight ahead. Blink normally."),
                       ("closed", c.closed_phase_s, "Now CLOSE your eyes and keep them closed.")]
        self.index, self.counting_down, self.t_phase = 0, True, time.monotonic()
        self.collector, self.results = None, {}
        # Machine-readable step for the phone, which follows it instead of running its own timers:
        # waiting_face | countdown_open | open | countdown_closed | closed, plus seconds left.
        self.step: str = "waiting_face"
        self.left_s: float | None = None

    def update(self, res) -> tuple[list[str], bool]:
        key, duration, prompt = self.phases[self.index]
        now = time.monotonic()
        if self.counting_down:
            if not res.face_present:
                self.t_phase = now
                self.step, self.left_s = "waiting_face", None
                return [prompt, "waiting for your face..."], False
            remaining = self.COUNTDOWN_S - (now - self.t_phase)
            if remaining > 0:
                self.step, self.left_s = f"countdown_{key}", round(remaining, 1)
                return [prompt, f"starting in {int(remaining) + 1}..."], False
            self.counting_down = False
            self.collector = self._collector_cls(self.cfg.settle_s).start()
        col = self.collector
        if res.face_present and res.ear_raw is not None:
            a = res.angles or (None, None, None)
            col.push(ear=res.ear_raw, h=res.gaze_h, v=res.gaze_v, yaw=a[0], pitch=a[1], roll=a[2])
        total = duration + self.cfg.settle_s
        self.step, self.left_s = key, round(max(0.0, total - col.elapsed), 1)
        if col.elapsed < total:
            left = "settle..." if col.settling else f"{max(0.0, total - col.elapsed):0.1f}s left"
            return [prompt, left], False
        self.results[key] = col.result()
        self.index += 1
        if self.index < len(self.phases):
            self.counting_down, self.t_phase = True, now
            return [self.phases[self.index][2], "get ready..."], False
        return [], True

    def build(self, directory: str):
        from dms_face.calibration import build_profile

        profile = build_profile(self.profile_name, self.results["open"], self.results["closed"])
        profile.save(directory)
        return profile


class _GivenLandmarks:
    """Stands in for the face subsystem's landmarker: returns the landmarks set for this frame."""

    def __init__(self) -> None:
        self.frame = None

    def process(self, frame_rgb, timestamp_s):
        return self.frame

    def close(self) -> None:
        pass


class Drowsiness:
    """Face subsystem on our frames: feed(view_gray, t) -> status dict for the page / overlay."""

    def __init__(self, width: int, height: int, model_path: str, backend: str = "litert",
                 profile_name: str = "default", profile_dir: str = "profiles"):
        from dms_face.calibration import DriverProfile
        from dms_face.config import Config

        cfg = Config()
        cfg.landmarker.backend = backend
        cfg.landmarker.model_path = model_path
        cfg.landmarker.num_threads = 1
        # The eyes-open reference adapts toward a percentile of the last 5 min of eye ratios. The
        # default 95th followed the widest moments and noise spikes on this far, noisy camera
        # (measured on the Pi: relaxed open eyes EAR p50 0.22, p90 0.31), so relaxed eyes read
        # 30-40 % open. Eyes are open most of the time and blinks sit in the low tail, so the
        # 60th percentile is the driver's typical open eye: relaxed eyes read ~100 %.
        cfg.calibration.adapt_percentile = 60.0
        self.cfg, self.w, self.h = cfg, width, height
        self.profile_name, self.profile_dir = profile_name, profile_dir
        self.profile, self.calibrated = DriverProfile.load_or_default(profile_name, profile_dir)
        self.pipe = self._new_pipeline()
        self.calib: Calibration | None = None
        self.banner: list[str] = []
        self.message = "" if self.calibrated else "not calibrated: press Calibrate"
        self.report = None

    def _new_pipeline(self):
        from dms_face.pipeline import FacePipeline

        pipe = FacePipeline(self.cfg, self.profile, self.w, self.h)
        pipe.landmarker.close()  # its own network is not needed: we pass our landmarks in
        self.given = _GivenLandmarks()
        pipe.landmarker = self.given
        return pipe

    def start_calibration(self) -> None:
        self.calib = Calibration(self.cfg, self.profile_name)
        self.message = "calibrating"

    def apply_phone_calibration(self, payload: dict) -> None:
        """Apply on the pipeline thread, using its current adapted baseline."""
        from dms_face.calibration import profile_from_phone

        try:
            current = replace(self.profile, ear_open=self.pipe.adapter.adapted_ear_open)
            profile = profile_from_phone(payload, current)
        except ValueError as e:
            self.message = f"calibration failed: {e}"
            return
        try:
            profile.save(self.profile_dir)
        except Exception:
            self.message = "calibration failed: could not save profile"
            return
        self.profile = profile
        try:
            self.pipe.close()
            self.pipe = self._new_pipeline()
        except Exception as e:
            self.message = f"calibration failed: {str(e) or type(e).__name__}"
            return
        self.calib, self.banner = None, []
        self.calibrated, self.message = True, "calibrated (phone)"

    def feed(self, t: float, landmarks) -> dict:
        """landmarks: (478, 2) driver-view pixels from the distraction pipeline, or None."""
        from dms_face.landmarker import LandmarkFrame

        if landmarks is None:
            self.given.frame = None
        else:
            pts = np.asarray(landmarks, dtype=np.float64)[:, :2]
            self.given.frame = LandmarkFrame(None, pts, len(pts) >= 478, None, None)
        res = self.pipe.process(None, t)
        if res.report is not None:
            self.report = res.report
        if self.calib is not None:
            self.banner, done = self.calib.update(res)
            if done:
                try:
                    self.profile = self.calib.build(self.profile_dir)
                    self.calibrated, self.message = True, "calibrated"
                    self.pipe.close()
                    self.pipe = self._new_pipeline()
                except ValueError as e:  # eyes did not separate: keep the old profile
                    self.message = f"calibration failed: {e}"
                self.calib, self.banner = None, []
        r = self.report
        return {
            "state": r.state.value if r else "starting",
            "reasons": list(r.reasons) if r else [],
            "perclos": round(r.perclos, 3) if r else None,
            "perclos_valid": bool(r.perclos_valid) if r else False,
            "blink_rate": round(r.blink_rate, 1) if r and r.blink_rate is not None else None,
            "closure_ms": round(r.closure_ms) if r else 0,
            "openness": None if res.openness_smooth is None else round(res.openness_smooth, 2),
            # raw eye ratio and the (adapted) eyes-open / closed references openness is scaled by
            "ear": None if res.ear_filtered is None else round(res.ear_filtered, 3),
            "ear_open": round(self.pipe.adapter.adapted_ear_open, 3),
            "ear_closed": round(self.profile.ear_closed, 3),
            "face": res.face_present,
            "calibrated": self.calibrated,
            "message": self.message,
            "calibration_step": self.calib.step if self.calib is not None else None,
            "calibration_left_s": self.calib.left_s if self.calib is not None else None,
            "ms": round(res.total_ms, 1),
        }

    def close(self) -> None:
        self.pipe.close()
