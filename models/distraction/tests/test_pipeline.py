"""Whole pipeline with injected fake detector / face mesh: timing of warning -> alert -> clear."""

import json

import numpy as np
from helpers import det, make_face

from rtdms_distraction.config import PipelineConfig, RulesConfig
from rtdms_distraction.eventlog import EventLog
from rtdms_distraction.pipeline import DistractionPipeline

FPS = 30


class Script:
    """Drives both fakes from one timeline: t -> (face kwargs or None, detections)."""

    def __init__(self, fn):
        self.fn = fn
        self.t = 0.0

    def detect(self, view):
        return self.fn(self.t)[1]

    def process(self, view, t):
        kw = self.fn(t)[0]
        return None if kw is None else make_face(**kw)


def timeline(t):
    neutral = {"pitch": 0.0}
    phone = [det("phone", 330, 450, 40, 70), det("hand", 335, 470, 70, 70)]
    if t < 2.0:
        return neutral, []
    if t < 4.0:
        return neutral, phone  # phone low in hand, eyes on road
    if t < 7.0:
        return {"pitch": 25.0}, phone  # looking down at it
    if t < 7.5:
        return None, phone  # face lost: hold
    return neutral, []


def build(fn):
    p = PipelineConfig()
    p.rectify.enabled = False
    p.hands.source = "detector"
    p.pose.enabled = False  # unit tests never load model files
    r = RulesConfig()
    r.baseline.duration_s = 1.0
    r.baseline.min_samples = 10
    s = Script(fn)
    return DistractionPipeline(p, r, (640, 640), detector=s, facemesh=s), s


def test_phone_in_hand_warning_then_alert_then_clear(tmp_path):
    pipe, s = build(timeline)
    log = EventLog(tmp_path)
    frame = np.zeros((640, 640), np.uint8)
    levels = {}
    for i in range(int(10 * FPS)):
        t = i / FPS
        s.t = t
        res = pipe.process(frame, t)
        levels[round(t, 2)] = res.behaviours["phone_in_hand"]["level"]
        log.update(t, res.behaviours)
        json.dumps(res.to_dict())  # per-frame output must be JSON-safe
    log.close(10.0)

    def first(level, after=0.0):
        return min(t for t, lv in levels.items() if lv == level and t >= after)

    warn = first("warning")
    alert = first("alert")
    assert 2.9 <= warn <= 3.3, warn  # ~1 s window coverage + 70 % ratio after onset at 2.0
    assert 5.9 <= alert <= 6.2, alert  # head down from 4.0, + 2.0 s
    assert levels[7.4] == "alert"  # face lost: state held
    end = first("none", after=7.5)
    assert 7.5 < end < 9.0
    events = [json.loads(x) for x in log.path.read_text().splitlines()]
    pih = [(e["event"], e.get("level")) for e in events if e.get("behaviour") == "phone_in_hand"]
    # Head back up while the phone is still smoothing out: alert steps down to warning, then ends.
    assert pih == [("start", "warning"), ("level", "alert"), ("level", "warning"), ("end", None)]


def test_no_detections_never_alerts():
    pipe, s = build(lambda t: ({"pitch": 0.0, "jaw": 0.2}, []))
    frame = np.zeros((640, 640), np.uint8)
    for i in range(int(5 * FPS)):
        s.t = i / FPS
        res = pipe.process(frame, i / FPS)
        assert res.level == "none"
    assert res.baseline["ready"]


def test_hand_at_ear_warning_after_dwell_then_alert_with_phone():
    hand = det("hand", 215, 270, 50, 50)  # centred in the driver's right ear zone
    phone = det("phone", 215, 265, 35, 70)

    def scene(t):
        if t < 1.0:
            return {"pitch": 0.0}, []
        if t < 5.0:
            return {"pitch": 0.0}, [hand]            # hand only: warning from ~4.0 s
        return {"pitch": 0.0}, [hand, phone]          # phone appears: alert

    pipe, s = build(scene)
    frame = np.zeros((640, 640), np.uint8)
    levels = {}
    for i in range(int(7 * FPS)):
        t = i / FPS
        s.t = t
        res = pipe.process(frame, t)
        levels[round(t, 2)] = res.behaviours["phone_right_ear"]["level"]
        assert res.variant == "hands"  # no pose / classifier loaded
        assert set(res.ear_levels) == {"hands", "hands+pose", "hands+pose+clf"}
    first_warn = min(t for t, lv in levels.items() if lv == "warning")
    assert 3.9 <= first_warn <= 4.1, first_warn
    assert levels[4.9] == "warning"
    assert levels[6.9] == "alert"
