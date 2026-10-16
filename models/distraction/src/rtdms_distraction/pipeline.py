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
from .rules import Baseline, FrameEvidence, RuleEngine, face_scale
from .smoothing import BehaviourSmoother
from .types import Detection, FaceObservation

LEVEL_RANK = {"none": 0, "warning": 1, "alert": 2}


@dataclass
class FrameResult:
    t: float
    view: np.ndarray  # driver view, gray or BGR (for the overlay; never logged)
    face: FaceObservation | None
    detections: list[Detection]
    evidence: FrameEvidence
    behaviours: dict[str, dict[str, Any]]
    level: str
    baseline: dict[str, Any]
    timings_ms: dict[str, float] = field(default_factory=dict)
    detector_ran: bool = False
    # Ear behaviours' level under each hand-at-ear evidence set (guided-mode comparison), and
    # the set this result reports.
    ear_levels: dict[str, dict[str, str]] = field(default_factory=dict)
    variant: str = "hands"
    person: Any = None  # driver's pose (pose.Person) or None
    clf: dict[str, float] | None = None  # ear-crop classifier, smoothed P(phone) per ear
    mouth: dict[str, float] | None = None  # mouth-crop classifier, smoothed class probabilities
    clf_alt: dict[str, dict[str, float]] = field(default_factory=dict)  # extra ear classifiers

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
                 detector=None, facemesh=None, hands=None, pose=None, ear_clf=None):
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
        # Simple mode: detector + face mesh only (no hands, pose or crop classifiers).
        self.simple = None
        if rcfg.mode == "simple":
            from .simple_rules import SimpleRules

            self.simple = SimpleRules(rcfg.simple)
            hands = None
            pcfg.hands.source = "off"
            pcfg.pose.enabled = False
            pcfg.ear_classifier.enabled = pcfg.mouth_classifier.enabled = False
        self.detector, self.facemesh, self.hands = detector, facemesh, hands
        if pose is None and pcfg.pose.enabled:
            try:
                from .pose import PoseEstimator
                pose = PoseEstimator(pcfg.pose)
            except (FileNotFoundError, ImportError) as e:
                print(f"[pipeline] pose disabled: {e}")
        if ear_clf is None and pcfg.ear_classifier.enabled:
            try:
                from .ear_clf import EarClassifier
                ear_clf = EarClassifier(pcfg.ear_classifier)
            except (FileNotFoundError, ImportError) as e:
                print(f"[pipeline] ear classifier disabled: {e}")
        mouth_clf = None
        if pcfg.mouth_classifier.enabled:
            try:
                from .ear_clf import MouthClassifier
                mouth_clf = MouthClassifier(pcfg.mouth_classifier)
            except (FileNotFoundError, ImportError) as e:
                print(f"[pipeline] mouth classifier disabled: {e}")
        self.pose, self.ear_clf, self.mouth_clf = pose, ear_clf, mouth_clf
        # Run-time switches (live.py keys p / c). A stage that is not loaded stays off.
        self.pose_on = pose is not None
        self.clf_on = ear_clf is not None  # ear AND mouth classifiers (key c)
        self._person = None
        self._clf_face, self._clf_face_t = None, 0.0  # last face, for crops while it is hidden
        self.ear_alts: dict = {}  # extra ear classifiers scored side by side (add_ear_model)

        hands_available = pcfg.hands.source != "off"
        self.rules = RuleEngine(rcfg, pcfg.driver_side, hands_available, (vw, vh))
        self.smoothers = {b: BehaviourSmoother(rcfg.smoothing) for b in BEHAVIOURS}
        self._i = 0
        self._dets: list[Detection] = []
        self._hands: list[Detection] = []

    # -- live controls (scripts/live.py) ---------------------------------------

    def set_detector(self, detector, hands_source: str) -> None:
        """Swap the detector at run time. hands_source: mediapipe (COCO models) | detector
        (models with a hand class)."""
        self.detector = detector
        self.pcfg.hands.source = hands_source
        if hands_source == "mediapipe" and self.hands is None:
            from .hands import MediaPipeHands
            self.hands = MediaPipeHands(self.pcfg.hands)
        self._dets, self._hands = [], []

    def add_ear_model(self, name: str, cfg) -> str:
        """Score one more ear-crop classifier on the same crops (guided comparison). Its setup
        is hands+pose+<this classifier>; returns the setup name."""
        from .ear_clf import EarClassifier

        self.ear_alts[name] = EarClassifier(cfg)
        return self.rules.add_clf_variant(name)

    def reset_baseline(self) -> None:
        b = self.rcfg.baseline
        self.rules.baseline = Baseline(b.duration_s, b.min_samples)

    # -- per frame -------------------------------------------------------------

    def process(self, frame: np.ndarray, t: float) -> FrameResult:
        """frame: grayscale (H, W) as on the IR camera, or BGR (H, W, 3) (live colour mode)."""
        tm: dict[str, float] = {}
        p = self.pcfg

        t0 = time.perf_counter()
        view = self.roi.apply(frame)
        if view.ndim == 2:  # gray x3: channel order is irrelevant
            det_in = face_in = cv2.cvtColor(view, cv2.COLOR_GRAY2RGB)
        else:  # detector takes BGR (Ultralytics convention), MediaPipe takes RGB
            det_in, face_in = view, cv2.cvtColor(view, cv2.COLOR_BGR2RGB)
        tm["rectify"] = (time.perf_counter() - t0) * 1000

        ran = self._i % max(1, p.detector.every_n) == 0
        t0 = time.perf_counter()
        if ran:
            self._dets = self.detector.detect(det_in)
        tm["detect"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        face = self.facemesh.process(face_in, t)
        tm["facemesh"] = (time.perf_counter() - t0) * 1000

        if self.simple is not None:
            return self._simple_result(view, face, t, tm, ran)

        t0 = time.perf_counter()
        if self.hands is not None and self._i % max(1, p.hands.every_n) == 0:
            self._hands = self.hands.detect(face_in, t)
        tm["hands"] = (time.perf_counter() - t0) * 1000

        # Pose (every Nth frame) and the ear-crop classifier feed the hand-at-ear rule.
        t0 = time.perf_counter()
        if self.pose is not None and self._i % max(1, p.pose.every_n) == 0:
            from .pose import driver_person
            self._person = driver_person(self.pose.detect(det_in),
                                         face.center if face is not None else None)
        tm["pose"] = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        clf = mouth = None
        clf_alt: dict[str, dict[str, float]] = {}
        if face is not None:
            self._clf_face, self._clf_face_t = face, t
        held, age = self._clf_face, t - self._clf_face_t
        if held is not None:
            fw = face_scale(held)
            if self.ear_clf is not None and age <= p.ear_classifier.face_hold_s:
                clf = self.ear_clf.update(det_in, held, fw)
            if age <= p.ear_classifier.face_hold_s:
                clf_alt = {n: m.update(det_in, held, fw) for n, m in self.ear_alts.items()}
            if self.mouth_clf is not None and age <= p.mouth_classifier.face_hold_s:
                mouth = self.mouth_clf.update(det_in, held, fw)
        tm["crop_clf"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        dets = [d for d in self._dets if d.cls != "hand" or p.hands.source == "detector"]
        dets += self._hands if p.hands.source == "mediapipe" else []
        ev = self.rules.evaluate(t, face, dets, person=self._person if self.pose else None,
                                 clf=clf, mouth_p=mouth if self.clf_on or self.ear_clf is None
                                 else None, clf_alt=clf_alt)
        variant = self.variant
        dwell = self.rcfg.hand_at_ear.dwell_s
        behaviours = {}
        ear_levels: dict[str, dict[str, str]] = {v: {} for v in self.rules.variants}
        for b in BEHAVIOURS:
            e = ev.behaviours[b]
            s = self.smoothers[b].update(t, e.active, e.confidence)
            level = self.rcfg.levels[b] if s.active else "none"
            extra = {}
            if b == "phone_in_hand" and s.active and \
                    ev.head_down_s >= self.rcfg.phone_in_hand.alert_after_down_s:
                level = "alert"
            if b in ev.ears:
                # Phone at an ear: a smoothed phone box -> ALERT; else a hand held at the ear
                # >= dwell -> WARNING, ALERT if a phone (box or classifier) was seen meanwhile.
                for v in self.rules.variants:
                    d_s, seen = ev.ears[b].variants.get(v, (0.0, False))
                    lv = "alert" if s.active else (("alert" if seen else "warning")
                                                   if d_s >= dwell else "none")
                    ear_levels[v][b] = lv
                level = ear_levels[variant][b]
                ee = ev.ears[b]
                extra = {"hand_s": round(ee.variants.get(variant, (0.0, False))[0], 2),
                         "hand_box": ee.hand_box, "pose": ee.pose,
                         "clf_p": None if ee.clf_p is None else round(ee.clf_p, 3)}
            behaviours[b] = {
                "active": level != "none", "level": level,
                "confidence": round(s.confidence, 3), "ratio": round(s.ratio, 2),
                "raw": e.active, "holding": s.holding, "why": e.why, **extra,
            }
        level = max((v["level"] for v in behaviours.values()), key=LEVEL_RANK.__getitem__)
        tm["rules"] = (time.perf_counter() - t0) * 1000

        bl = self.rules.baseline
        baseline = {"ready": bl.ready, "progress": round(bl.progress(t), 2),
                    "pitch": _r(bl.pitch, 2), "yaw": _r(bl.yaw, 2), "gaze": _r(bl.gaze)}
        self._i += 1
        return FrameResult(t, view, face, dets, ev, behaviours, level, baseline, tm, ran,
                           ear_levels, variant, self._person if self.pose_on else None, clf,
                           mouth, clf_alt)

    def _simple_result(self, view, face, t: float, tm: dict, ran: bool) -> FrameResult:
        t0 = time.perf_counter()
        dets = [d for d in self._dets if d.cls in ("phone", "drink", "food")]
        behaviours = self.simple.update(t, face, dets)
        level = max((v["level"] for v in behaviours.values()), key=LEVEL_RANK.__getitem__)
        zone = self.simple.zone
        ev = FrameEvidence(behaviours={}, head_down=None, head_down_s=0.0, chewing=None,
                           zones={"mouth": zone} if zone is not None else {},
                           stale_face=face is None and zone is not None)
        tm["rules"] = (time.perf_counter() - t0) * 1000
        # No head-pose rule in simple mode, so no per-drive baseline to wait for.
        baseline = {"ready": True, "progress": 1.0, "pitch": None, "yaw": None, "gaze": None}
        self._i += 1
        return FrameResult(t, view, face, dets, ev, behaviours, level, baseline, tm, ran,
                           variant="simple")

    @property
    def variant(self) -> str:
        if self.pose_on and self.clf_on:
            return "hands+pose+clf"
        return "hands+pose" if self.pose_on else "hands"

    def close(self) -> None:
        for part in (self.facemesh, self.hands):
            if part is not None and hasattr(part, "close"):
                part.close()
