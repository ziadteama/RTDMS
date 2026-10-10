"""Per-frame rules: detections + face -> raw evidence for each behaviour.

Everything here is geometry in the rectified driver view, scaled by the driver's own face size,
plus two small pieces of state: the per-drive head-pose baseline and the chewing analyser.
Temporal smoothing lives in smoothing.py; this module answers "does THIS frame look like X?".

Evidence.active is tri-state: True / False, or None when the frame cannot be judged (no face).
None makes the smoother hold its previous state instead of counting a negative.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .config import BEHAVIOURS, ChewingConfig, EarZoneConfig, RulesConfig
from .types import Box, Detection, FaceObservation, box_gap, overlap_min, point_box_dist

DRIVER_RIGHT_EAR, DRIVER_LEFT_EAR = 234, 454
FOREHEAD, CHIN = 10, 152
# |10-152| / |234-454| on MediaPipe's canonical face; used to keep the face-size unit stable when
# the head turns (width shrinks under yaw, height does not).
HEIGHT_PER_WIDTH = 1.1


def face_scale(face: FaceObservation) -> float:
    """The 'fw' unit of rules.yaml: face width, made robust to head turns."""
    lm = face.landmarks
    width = float(np.linalg.norm(lm[DRIVER_LEFT_EAR] - lm[DRIVER_RIGHT_EAR]))
    height = float(np.linalg.norm(lm[CHIN] - lm[FOREHEAD]))
    return max(width, height / HEIGHT_PER_WIDTH)


@dataclass
class Evidence:
    active: bool | None
    confidence: float = 0.0
    why: str = ""


# --------------------------------------------------------------------------- baseline


class Baseline:
    """Median head pitch / yaw / gaze over the first seconds of the drive with a face."""

    def __init__(self, duration_s: float, min_samples: int):
        self.duration_s, self.min_samples = duration_s, min_samples
        self._t0: float | None = None
        self._pitch: list[float] = []
        self._yaw: list[float] = []
        self._gaze: list[float] = []
        self.pitch = self.yaw = self.gaze = None
        self.gaze_source: str | None = None

    @property
    def ready(self) -> bool:
        return self.pitch is not None

    def update(self, t: float, face: FaceObservation) -> None:
        if self.ready or face.pitch_deg is None:
            return
        if self._t0 is None:
            self._t0 = t
        self._pitch.append(face.pitch_deg)
        self._yaw.append(face.yaw_deg if face.yaw_deg is not None else 0.0)
        if face.gaze_down is not None:
            self._gaze.append(face.gaze_down)
            self.gaze_source = face.gaze_source
        if t - self._t0 >= self.duration_s and len(self._pitch) >= self.min_samples:
            self.pitch = float(np.median(self._pitch))
            self.yaw = float(np.median(self._yaw))
            self.gaze = float(np.median(self._gaze)) if self._gaze else None

    def progress(self, t: float) -> float:
        if self.ready:
            return 1.0
        if self._t0 is None:
            return 0.0
        return min((t - self._t0) / self.duration_s, len(self._pitch) / self.min_samples, 1.0)


# --------------------------------------------------------------------------- chewing


@dataclass
class ChewingResult:
    chewing: bool
    band_fraction: float = 0.0
    dominant_hz: float = 0.0
    amplitude: float = 0.0
    lips_closed_fraction: float = 0.0
    why: str = ""


class ChewingDetector:
    """Rhythmic jaw movement at chewing rate with the lips mostly closed.

    Chewing is ~1-2 Hz jaw oscillation with closed lips. Talking moves the jaw too, but faster,
    irregularly and with the lips apart; singing holds the mouth open. So the test is: enough
    jaw amplitude, most of its power in the chewing band, and lips closed most of the time.
    """

    def __init__(self, cfg: ChewingConfig):
        self.cfg = cfg
        self._buf: deque[tuple[float, float, float]] = deque()
        self.source = "blendshape"

    def update(self, t: float, jaw: float | None, source: str, lip_ratio: float) -> None:
        if jaw is None:
            return
        if source != self.source:
            self._buf.clear()  # different units; do not mix them in one window
            self.source = source
        self._buf.append((t, jaw, lip_ratio))
        while self._buf and t - self._buf[0][0] > self.cfg.window_s:
            self._buf.popleft()

    def analyze(self) -> ChewingResult:
        c = self.cfg
        if len(self._buf) < 8 or self._buf[-1][0] - self._buf[0][0] < c.min_span_s:
            return ChewingResult(False, why="warming up")
        t, jaw, lip = (np.array(v) for v in zip(*self._buf, strict=True))
        lips_closed = float(np.mean(lip < c.lips_closed_ratio))

        grid = np.arange(t[0], t[-1], 1.0 / c.resample_hz)
        sig = np.interp(grid, t, jaw)
        sig = sig - np.polyval(np.polyfit(grid - grid[0], sig, 1), grid - grid[0])
        amp = float(np.std(sig))

        spec = np.abs(np.fft.rfft(sig * np.hanning(len(sig)))) ** 2
        freqs = np.fft.rfftfreq(len(sig), 1.0 / c.resample_hz)
        total_mask = (freqs >= 0.3) & (freqs <= 7.0)
        band_mask = (freqs >= c.band_hz[0]) & (freqs <= c.band_hz[1])
        total = float(spec[total_mask].sum())
        band_frac = float(spec[band_mask].sum()) / total if total > 0 else 0.0
        dom = float(freqs[total_mask][np.argmax(spec[total_mask])]) if total > 0 else 0.0

        min_amp = c.min_amplitude_blendshape if self.source == "blendshape" \
            else c.min_amplitude_geometric
        checks = [
            (amp >= min_amp, f"amp {amp:.3f}<{min_amp}"),
            (band_frac >= c.min_band_fraction, f"band {band_frac:.2f}<{c.min_band_fraction}"),
            (c.band_hz[0] <= dom <= c.band_hz[1], f"freq {dom:.1f}Hz"),
            (lips_closed >= c.min_lips_closed_fraction, f"lips open {1 - lips_closed:.0%}"),
        ]
        failed = [why for ok, why in checks if not ok]
        return ChewingResult(not failed, band_frac, dom, amp, lips_closed, ", ".join(failed))


# --------------------------------------------------------------------------- engine


# Hand-at-ear evidence sets compared in guided mode. Every variant sees the same frames; the
# pipeline reports the one matching what is enabled.
EAR_VARIANTS = ("hands", "hands+pose", "hands+pose+clf")
# Eye line / jaw line landmarks per face side: outer eye corner, jaw angle.
EYE_OF = {DRIVER_RIGHT_EAR: 33, DRIVER_LEFT_EAR: 263}
JAW_OF = {DRIVER_RIGHT_EAR: 172, DRIVER_LEFT_EAR: 397}


@dataclass
class HandEpisode:
    """One ear, one evidence variant: how long a hand has been at the ear (tolerating short
    misses), and whether a phone was seen during that time."""

    gap_s: float
    start: float | None = None
    last: float | None = None
    phone_seen: bool = False

    def update(self, t: float, hand: bool | None, phone: bool) -> None:
        if hand is None:  # cannot judge (face lost too long): hold
            return
        if hand:
            if self.last is None or t - self.last > self.gap_s:
                self.start, self.phone_seen = t, False
            self.last = t
        elif self.last is not None and t - self.last > self.gap_s:
            self.start = self.last = None
            self.phone_seen = False
        if phone and self.start is not None:
            self.phone_seen = True

    def dwell(self, t: float) -> float:
        return t - self.start if self.start is not None else 0.0


@dataclass
class EarEvidence:
    """Per ear, this frame."""

    hand_box: bool | None = None  # a hand box centred in the ear zone
    pose: bool | None = None  # pose wrist rule
    phone_box: bool = False  # a phone box overlapping the ear zone
    clf_p: float | None = None  # ear-crop classifier, smoothed P(phone)
    variants: dict[str, tuple[float, bool]] = field(default_factory=dict)  # dwell_s, phone_seen


@dataclass
class FrameEvidence:
    behaviours: dict[str, Evidence]
    head_down: bool | None
    head_down_s: float
    chewing: ChewingResult | None
    # Geometry the overlay draws; all in driver-view pixels.
    zones: dict[str, Box] = field(default_factory=dict)
    scale: float | None = None
    ears: dict[str, EarEvidence] = field(default_factory=dict)
    stale_face: bool = False  # face lost; zones come from the last face (item 4)
    wrists: list[tuple[float, float]] = field(default_factory=list)  # pose wrists (overlay)


class RuleEngine:
    def __init__(self, cfg: RulesConfig, driver_side: str, hands_available: bool,
                 view_size: tuple[int, int]):
        self.cfg = cfg
        self.hands_available = hands_available
        self.view_w, self.view_h = view_size
        # LHD (driver on image-right): camera is to the driver's right, so the right ear faces it.
        near = DRIVER_RIGHT_EAR if driver_side == "right" else DRIVER_LEFT_EAR
        self.ears = {
            "phone_right_ear": (DRIVER_RIGHT_EAR, cfg.ears.near if near == DRIVER_RIGHT_EAR
                                else cfg.ears.far),
            "phone_left_ear": (DRIVER_LEFT_EAR, cfg.ears.near if near == DRIVER_LEFT_EAR
                               else cfg.ears.far),
        }
        self.baseline = Baseline(cfg.baseline.duration_s, cfg.baseline.min_samples)
        self.chewing = ChewingDetector(cfg.eating.chewing)
        self._last_food_t: float | None = None
        self._last_food_conf = 0.0
        self._down_since: float | None = None
        self._last_face: FaceObservation | None = None
        self._last_face_t = -1e9
        gap = cfg.hand_at_ear.gap_s
        self.episodes = {v: {b: HandEpisode(gap) for b in self.ears} for v in EAR_VARIANTS}

    # -- geometry -------------------------------------------------------------

    def ear_zone(self, face: FaceObservation, ear: int, z: EarZoneConfig, s: float) -> Box:
        lm = face.landmarks
        p = lm[ear]
        c = 0.5 * (lm[DRIVER_RIGHT_EAR] + lm[DRIVER_LEFT_EAR])
        u = p - c
        n = np.linalg.norm(u)
        u = u / n if n > 1e-6 else np.array([1.0 if ear == DRIVER_LEFT_EAR else -1.0, 0.0])
        d = np.array([-u[1], u[0]])
        if d[1] < 0:
            d = -d  # perpendicular that points down the face
        ctr = p + z.outward * s * u + z.down * s * d
        box = Box.around(ctr[0], ctr[1], z.half_width * s, z.half_height * s)
        if z.inward > 0:  # reach behind the head: up to `inward` fw inside the ear landmark
            if u[0] > 0:
                box = Box(min(box.x1, p[0] - z.inward * s), box.y1, box.x2, box.y2)
            else:
                box = Box(box.x1, box.y1, max(box.x2, p[0] + z.inward * s), box.y2)
        e = self.cfg.ears
        if e.eye_to_jaw:  # vertical extent: eye line .. jaw line
            y1 = lm[EYE_OF[ear]][1] - e.eye_margin * s
            y2 = lm[JAW_OF[ear]][1] + e.jaw_margin * s
            if y2 > y1:
                box = Box(box.x1, y1, box.x2, y2)
        return box

    def mouth_zone(self, face: FaceObservation, s: float) -> Box:
        m = face.mouth_center
        d = self.cfg.drinking
        return Box.around(m[0], m[1], d.mouth_half_width * s, d.mouth_half_height * s)

    def _in_holder(self, b: Box) -> bool:
        for x, y, w, h in self.cfg.phone_in_hand.holder_zones:
            if x * self.view_w <= b.cx <= (x + w) * self.view_w and \
                    y * self.view_h <= b.cy <= (y + h) * self.view_h:
                return True
        return False

    def _pose_wrist_ears(self, face: FaceObservation, s: float, person) -> tuple[set, list]:
        """Ears (landmark ids) a raised wrist is at, per the pose wrist rule; wrist points."""
        if person is None:
            return set(), []
        from .pose import ARMS

        h = self.cfg.hand_at_ear
        lm = face.landmarks
        k = person.kpts
        hit, wrists = set(), []
        for sh, el, wr in ARMS:
            if k[wr, 2] < h.kpt_conf:
                continue
            w = k[wr, :2]
            wrists.append((float(w[0]), float(w[1])))
            ear = min((DRIVER_RIGHT_EAR, DRIVER_LEFT_EAR),
                      key=lambda e, w=w: float(np.linalg.norm(w - lm[e])))
            if np.linalg.norm(w - lm[ear]) > h.wrist_ear_max * s:
                continue
            if w[1] < lm[EYE_OF[ear]][1] - self.cfg.ears.eye_margin * s:
                continue  # above the eye line: hand on the head, not a call
            if k[el, 2] >= h.kpt_conf and k[sh, 2] >= h.kpt_conf:
                if k[el, 1] > k[sh, 1] + h.elbow_max_below_shoulder * s:
                    continue  # elbow hanging down by the body
            elif not h.elbow_unseen_ok:
                continue
            hit.add(ear)
        return hit, wrists

    # -- per frame ------------------------------------------------------------

    def evaluate(self, t: float, face: FaceObservation | None, dets: list[Detection],
                 person=None, clf: dict[str, float] | None = None) -> FrameEvidence:
        """person: the driver's pose (pose.Person) or None; clf: per ear behaviour, the ear-crop
        classifier's smoothed P(phone), or None when the classifier is off."""
        stale = False
        if face is None:
            # Item 4: within face_geometry_hold_s, keep the last face's zones so a phone or cup
            # hiding the face still counts from the detector alone. Face-only signals (chewing,
            # head pose, phone below the chin) pause.
            if self._last_face is not None and \
                    t - self._last_face_t <= self.cfg.smoothing.face_geometry_hold_s:
                face, stale = self._last_face, True
            else:
                unknown = {b: Evidence(None, why="no face") for b in BEHAVIOURS}
                down_s = t - self._down_since if self._down_since is not None else 0.0
                ears = {b: EarEvidence() for b in self.ears}
                for v in EAR_VARIANTS:
                    for b, ep in self.episodes[v].items():
                        ep.update(t, None, False)
                        ears[b].variants[v] = (ep.dwell(t), ep.phone_seen)
                return FrameEvidence(unknown, None, down_s, None, ears=ears)
        else:
            self._last_face, self._last_face_t = face, t
            self.baseline.update(t, face)
            self.chewing.update(t, face.jaw_open, face.jaw_source, face.lip_ratio)

        s = face_scale(face)
        lm = face.landmarks
        phones = [d for d in dets if d.cls == "phone"]
        hands = [d for d in dets if d.cls == "hand"]
        held = [d.box for d in dets if d.cls in ("drink", "food")]
        out: dict[str, Evidence] = {}
        zones: dict[str, Box] = {}

        # Phone at an ear: each phone box goes to the ear zone it overlaps most.
        ear_zones = {b: self.ear_zone(face, idx, z, s) for b, (idx, z) in self.ears.items()}
        zones.update(ear_zones)
        at_ear: dict[str, Evidence] = {b: Evidence(False) for b in ear_zones}
        used: set[int] = set()
        for i, ph in enumerate(phones):
            best = max(ear_zones, key=lambda b, ph=ph: overlap_min(ph.box, ear_zones[b]))
            ov = overlap_min(ph.box, ear_zones[best])
            if ov >= self.cfg.ears.min_overlap:
                used.add(i)
                if ph.conf > at_ear[best].confidence:
                    at_ear[best] = Evidence(True, ph.conf, f"phone at ear, overlap {ov:.2f}")
        out.update(at_ear)

        # Hand at an ear (both ears): hand box centred in the zone, or the pose wrist rule. A
        # hand holding a cup or food is not holding a phone.
        pose_ears, wrists = self._pose_wrist_ears(face, s, person)
        ears: dict[str, EarEvidence] = {}
        for b, (idx, _) in self.ears.items():
            z = ear_zones[b]
            box_hit = any(z.x1 <= h.box.cx <= z.x2 and z.y1 <= h.box.cy <= z.y2 and
                          not any(overlap_min(h.box, o) > 0.3 for o in held) for h in hands)
            p_clf = clf.get(b) if clf else None
            ev = EarEvidence(hand_box=box_hit if self.hands_available else None,
                             pose=(idx in pose_ears) if person is not None else None,
                             phone_box=bool(at_ear[b].active), clf_p=p_clf)
            clf_phone = p_clf is not None and p_clf >= self.cfg.hand_at_ear.classifier_phone
            hand = {"hands": ev.hand_box,
                    "hands+pose": bool(ev.hand_box) or bool(ev.pose),
                    "hands+pose+clf": bool(ev.hand_box) or bool(ev.pose)}
            phone = {"hands": ev.phone_box, "hands+pose": ev.phone_box,
                     "hands+pose+clf": ev.phone_box or clf_phone}
            for v in EAR_VARIANTS:
                ep = self.episodes[v][b]
                ep.update(t, hand[v], phone[v])
                ev.variants[v] = (ep.dwell(t), ep.phone_seen)
            ears[b] = ev

        # Head / gaze down relative to the baseline (needs a live face).
        if stale:
            head_down = None
        else:
            head_down = self._head_down(face)
            if head_down:
                self._down_since = t if self._down_since is None else self._down_since
            else:
                self._down_since = None
        down_s = t - self._down_since if self._down_since is not None else 0.0

        # Phone held low, in a hand, not in a holder (needs a live face: chin position).
        pih = self.cfg.phone_in_hand
        chin_y = lm[CHIN][1]
        out["phone_in_hand"] = Evidence(None, why="face lost") if stale else Evidence(False)
        for i, ph in enumerate(phones if not stale else []):
            if i in used or ph.box.cy < chin_y + pih.below_chin * s or self._in_holder(ph.box):
                continue
            if self.hands_available and pih.require_hand:
                gap = min((box_gap(ph.box, h.box) for h in hands), default=float("inf"))
                if gap > pih.hand_max_gap * s:
                    continue
                why = f"phone below face, hand gap {gap / s:.2f} fw"
            else:
                why = "phone below face (hands not checked)"
            if ph.conf > out["phone_in_hand"].confidence:
                out["phone_in_hand"] = Evidence(True, ph.conf, why)

        # Drinking: container at the mouth; head tilted back raises confidence.
        mouth = self.mouth_zone(face, s)
        zones["mouth"] = mouth
        dk = self.cfg.drinking
        out["drinking"] = Evidence(False)
        for d in dets:
            if d.cls != "drink":
                continue
            ov = overlap_min(d.box, mouth)
            if ov >= dk.min_overlap:
                conf = d.conf
                dp = None if stale else self._pitch_delta(face)
                if dp is not None and -dp >= dk.pitch_up_deg:
                    conf = min(1.0, conf * dk.pitch_up_bonus)
                if conf > out["drinking"].confidence:
                    why = f"drink at mouth, overlap {ov:.2f}" + (" (last face)" if stale else "")
                    out["drinking"] = Evidence(True, conf, why)

        # Eating: food near the mouth recently AND chewing now (chewing needs a live face).
        ea = self.cfg.eating
        mx, my = face.mouth_center
        for d in dets:
            if d.cls == "food" and point_box_dist(mx, my, d.box) <= ea.food_mouth_max_dist * s:
                self._last_food_t, self._last_food_conf = t, d.conf
        chew = None if stale else self.chewing.analyze()
        recent = self._last_food_t is not None and t - self._last_food_t <= ea.food_memory_s
        if stale:
            out["eating"] = Evidence(None, why="face lost")
        elif recent and chew.chewing:
            out["eating"] = Evidence(True, self._last_food_conf,
                                     f"food {t - self._last_food_t:.1f}s ago + chewing "
                                     f"{chew.dominant_hz:.1f}Hz")
        else:
            why = "no food at mouth recently" if not recent else f"not chewing ({chew.why})"
            out["eating"] = Evidence(False, why=why)

        return FrameEvidence(out, head_down, down_s, chew, zones, s, ears, stale, wrists)

    def _pitch_delta(self, face: FaceObservation) -> float | None:
        if not self.baseline.ready or face.pitch_deg is None:
            return None
        return face.pitch_deg - self.baseline.pitch

    def _head_down(self, face: FaceObservation) -> bool | None:
        if not self.baseline.ready:
            return None
        hd = self.cfg.head_down
        dp = self._pitch_delta(face)
        if dp is not None and dp >= hd.pitch_deg:
            return True
        if face.gaze_down is not None and self.baseline.gaze is not None:
            thr = hd.gaze_down if face.gaze_source == "blendshape" else hd.gaze_down_iris
            if face.gaze_down - self.baseline.gaze >= thr:
                return True
        return False
