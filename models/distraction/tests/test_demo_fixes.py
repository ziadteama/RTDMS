"""Demo fixes: eating / texting never reported; no drowsiness verdict right after calibrating."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hybrid  # noqa: E402
from hybrid_alerts import CLASSES  # noqa: E402


def make_hybrid(monkeypatch, top: str, p: float = 0.9):
    h = object.__new__(hybrid.Hybrid)
    probs = np.zeros(len(CLASSES))
    probs[CLASSES.index(top)], probs[CLASSES.index("other")] = p, 0.08
    h.action = lambda up: probs
    h.ear = lambda crop: np.array([0.0])
    h.logic = hybrid.AlertLogic(alerts=("call",), use_talk=False, phone_p=hybrid.EAR_P)
    h.last, h.boxes = {}, None
    monkeypatch.setattr(hybrid, "crops", lambda g, lm: ((None, None, None, None), None, 0.0))
    return h


@pytest.mark.parametrize("dropped", ["eating", "texting"])
def test_eating_and_texting_are_never_reported(monkeypatch, dropped):
    h = make_hybrid(monkeypatch, dropped)
    for i in range(20):  # 2 s of frames: texting would have alerted before
        out = h.feed(i * 0.1, np.zeros((4, 4), np.uint8), np.zeros((478, 2)))
    assert out["action"] == "other" and out["p"] == 0.08
    assert out["texting"] is False and out["lap"] is None


def test_drinking_score_reported_even_when_other_wins(monkeypatch):
    h = make_hybrid(monkeypatch, "other", 0.5)
    probs = np.zeros(len(CLASSES))
    probs[CLASSES.index("other")], probs[CLASSES.index("drinking")] = 0.55, 0.4
    h.action = lambda up: probs
    out = h.feed(0.1, np.zeros((4, 4), np.uint8), np.zeros((478, 2)))
    assert out["action"] == "other" and out["p_drinking"] == 0.4
    assert h.feed(0.2, None, None)["p_drinking"] is None  # no face


def test_call_still_reported(monkeypatch):
    out = make_hybrid(monkeypatch, "call").feed(0.0, np.zeros((4, 4), np.uint8),
                                                np.zeros((478, 2)))
    assert out["action"] == "call" and out["ear"] == 0.0


dms_face = pytest.importorskip("dms_face.blink")
import drowsiness  # noqa: E402


def res(eye, state):
    report = SimpleNamespace(state=SimpleNamespace(value=state), reasons=[], perclos=1.0,
                             perclos_valid=True, blink_rate=None, closure_ms=3000)
    return SimpleNamespace(eye_state=eye, report=report, openness_smooth=None, ear_filtered=None,
                           angles=None, gaze_h=None, gaze_v=None, gaze_dev=None,
                           face_present=True, total_ms=0.0)


class Pipe:
    def __init__(self, *results):
        self.results, self.closed = list(results), False
        self.adapter = SimpleNamespace(adapted_ear_open=0.3)

    def process(self, frame, t):
        return self.results.pop(0)

    def close(self):
        self.closed = True


def just_calibrated(pipe, fresh, deadline=10.0):
    d = object.__new__(drowsiness.Drowsiness)
    d.calib, d.message, d.calibrated, d.report = None, "calibrated", True, None
    d.profile, d.given = SimpleNamespace(ear_closed=0.05), SimpleNamespace(frame=None)
    d.pipe, d._new_pipeline, d.reopen_deadline = pipe, lambda: fresh, deadline
    return d


def test_no_verdict_until_the_eyes_open_after_calibration():
    Eye = dms_face.EyeState
    fresh = Pipe(res(Eye.OPEN, "alert"))
    d = just_calibrated(Pipe(res(Eye.CLOSED, "drowsy"), res(Eye.OPEN, "drowsy")), fresh)
    assert d.feed(1.0, None)["state"] == "starting"  # eyes still shut from the closed step
    assert d.feed(1.1, None)["state"] == "starting"  # eyes open: history restarts
    assert d.reopen_deadline is None and d.pipe is fresh
    assert d.feed(1.2, None)["state"] == "alert"


def test_grace_ends_after_the_deadline_even_with_eyes_shut():
    Eye = dms_face.EyeState
    fresh = Pipe(res(Eye.CLOSED, "drowsy"))
    d = just_calibrated(Pipe(res(Eye.CLOSED, "drowsy")), fresh, deadline=5.0)
    assert d.feed(5.0, None)["state"] == "starting"
    assert d.reopen_deadline is None
    assert d.feed(5.1, None)["state"] == "drowsy"  # still shut 5 s later: judged normally
