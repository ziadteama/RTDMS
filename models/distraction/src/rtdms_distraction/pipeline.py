"""One frame through every stage, with per-stage timing.

    gray frame -> ROI rectify -> (3-ch) -> detector (every Nth frame)
                                        -> face mesh (every frame)
                                        -> hands (MediaPipe, every Nth frame) | detector | off
               -> rules -> smoothing + hysteresis -> levels -> FrameResult

The module REPORTS behaviour states with a recommended level; the integrated system's fusion
stage owns the cabin buzzer (repo invariant, see docs/ARCHITECTURE.md).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from .calibration import FisheyeCalibration
from .config import BEHAVIOURS, PipelineConfig, RulesConfig, resolve_path
from .roi import DriverROI
from .rules import FrameEvidence, RuleEngine
from .smoothing import BehaviourSmoother
from .types import Detection, FaceObservation

LEVEL_RANK = {"none": 0, "warning": 1, "alert": 2}


@dataclass
class FrameResult:
    t: float
    view: np.ndarray  # gray driver view (for the overlay; never logged)
    face: FaceObservation | None
    detections: list[Detection]
    evidence: FrameEvidence
    behaviours: dict[str, dict[str, Any]]
    level: str
    baseline: dict[str, Any]
    timings_ms: dict[str, float] = field(default_factory=dict)
    detector_ran: bool = False

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe per-frame output (no image, no landmarks)."""
        f = self.face
        return {
            "t": round(self.t, 3),
            "level": self.level,
            "behaviours": self.behaviours,
            "face": None if f is None else {
                "pitch": _r(f.pitch_deg), "yaw": _r(f.yaw_deg), "gaze_down": _r(f.gaze_down),
                "gaze_source": f.gaze_source, "jaw": _r(f.jaw_open), "jaw_source": f.jaw_source,
                "lip_ratio": _r(f.lip_ratio),
            },
            "head_down": self.evidence.head_down,
            "head_down_s": round(self.evidence.head_down_s, 2),
            "chewing": None if self.evidence.chewing is None else {
                "chewing": self.evidence.chewing.chewing,
                "hz": round(self.evidence.chewing.dominant_hz, 2),
                "band": round(self.evidence.chewing.band_fraction, 2),
                "amp": round(self.evidence.chewing.amplitude, 4),
                "lips_closed": round(self.evidence.chewing.lips_closed_fraction, 2),
            },
            "detections": [{"cls": d.cls, "conf": round(d.conf, 3), "box": d.box.as_list(),
                            "src": d.source} for d in self.detections],
            "baseline": self.baseline,
            "timings_ms": {k: round(v, 2) for k, v in self.timings_ms.items()},
        }


def _r(v: float | None, n: int = 3) -> float | None:
    return None if v is None else round(float(v), n)


class DistractionPipeline:
    def __init__(self, pcfg: PipelineConfig, rcfg: RulesConfig, frame_size: tuple[int, int],
                 detector=None, facemesh=None, hands=None):
        """frame_size = (w, h) of the raw frames. detector / facemesh / hands may be injected
        (tests, replay); otherwise they are built from the config."""
        self.pcfg, self.rcfg = pcfg, rcfg
        cv2.setNumThreads(pcfg.threads.opencv)

        calib = None
        if pcfg.rectify.enabled:
            path = resolve_path(pcfg.rectify.calibration_file)
            if not path.is_file():
                raise FileNotFoundError(
                    f"{path} missing: run scripts/calibrate_fisheye.py, or set rectify.enabled: "
                    "false (--no-rectify) for non-fisheye sources")
            calib = FisheyeCalibration.load(path)
        r = pcfg.roi
        self.roi = DriverROI(frame_size[0], frame_size[1], r.rect, r.output_width,
                             r.output_height, calib, r.mask_polygons)
        vw, vh = self.roi.out_w, self.roi.out_h

        if detector is None:
            from .detector import make_detector
            detector = make_detector(pcfg.detector)
        if facemesh is None:
            from .facemesh import FaceMesh
            facemesh = FaceMesh(pcfg.facemesh, vw, vh, self.roi.intrinsics)
        if hands is None and pcfg.hands.source == "mediapipe":
            from .hands import MediaPipeHands
            hands = MediaPipeHands(pcfg.hands)
        self.detector, self.facemesh, self.hands = detector, facemesh, hands

        hands_available = pcfg.hands.source != "off"
        self.rules = RuleEngine(rcfg, pcfg.driver_side, hands_available, (vw, vh))
        self.smoothers = {b: BehaviourSmoother(rcfg.smoothing) for b in BEHAVIOURS}
        self._i = 0
        self._dets: list[Detection] = []
        self._hands: list[Detection] = []

    def process(self, gray: np.ndarray, t: float) -> FrameResult:
        tm: dict[str, float] = {}
        p = self.pcfg

        t0 = time.perf_counter()
        view = self.roi.apply(gray)
        view3 = cv2.cvtColor(view, cv2.COLOR_GRAY2RGB)
        tm["rectify"] = (time.perf_counter() - t0) * 1000

        ran = self._i % max(1, p.detector.every_n) == 0
        t0 = time.perf_counter()
        if ran:
            self._dets = self.detector.detect(view3)
        tm["detect"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        face = self.facemesh.process(view3, t)
        tm["facemesh"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        if self.hands is not None and self._i % max(1, p.hands.every_n) == 0:
            self._hands = self.hands.detect(view3, t)
        tm["hands"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        dets = [d for d in self._dets if d.cls != "hand" or p.hands.source == "detector"]
        dets += self._hands if p.hands.source == "mediapipe" else []
        ev = self.rules.evaluate(t, face, dets)
        behaviours = {}
        for b in BEHAVIOURS:
            e = ev.behaviours[b]
            s = self.smoothers[b].update(t, e.active, e.confidence)
            level = self.rcfg.levels[b] if s.active else "none"
            if b == "phone_in_hand" and s.active and \
                    ev.head_down_s >= self.rcfg.phone_in_hand.alert_after_down_s:
                level = "alert"
            behaviours[b] = {
                "active": s.active, "level": level, "confidence": round(s.confidence, 3),
                "ratio": round(s.ratio, 2), "raw": e.active, "holding": s.holding, "why": e.why,
            }
        level = max((v["level"] for v in behaviours.values()), key=LEVEL_RANK.__getitem__)
        tm["rules"] = (time.perf_counter() - t0) * 1000

        bl = self.rules.baseline
        baseline = {"ready": bl.ready, "progress": round(bl.progress(t), 2),
                    "pitch": _r(bl.pitch, 2), "yaw": _r(bl.yaw, 2), "gaze": _r(bl.gaze)}
        self._i += 1
        return FrameResult(t, view, face, dets, ev, behaviours, level, baseline, tm, ran)

    def close(self) -> None:
        for part in (self.facemesh, self.hands):
            if part is not None and hasattr(part, "close"):
                part.close()
