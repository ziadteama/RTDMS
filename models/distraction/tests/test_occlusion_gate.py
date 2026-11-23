"""Hand / phone / cup at the face must not count as closed eyes (stream.py occlusion gate)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stream  # noqa: E402


def test_hand_phone_cup_at_face_hide_the_eyes():
    for action in ("call", "texting", "drinking", "hand_on_face"):
        assert stream.occludes_eyes({"action": action, "p": 0.8})


def test_normal_low_confidence_or_no_face_do_not():
    assert not stream.occludes_eyes({"action": "normal", "p": 0.99})
    assert not stream.occludes_eyes({"action": "other", "p": 0.99})
    assert not stream.occludes_eyes({"action": "drinking", "p": 0.3})
    assert not stream.occludes_eyes({"action": None, "p": None})  # no face
    assert not stream.occludes_eyes(None)  # --hybrid off


def test_eating_is_never_reported(monkeypatch):
    import hybrid
    import numpy as np
    from hybrid_alerts import CLASSES, AlertLogic

    h = object.__new__(hybrid.Hybrid)
    probs = np.zeros(len(CLASSES))
    probs[CLASSES.index("eating")], probs[CLASSES.index("other")] = 0.9, 0.08
    h.action = lambda up: probs
    h.ear = h.lap = lambda crop: np.array([0.0])
    h.logic, h.last, h.boxes = AlertLogic(alerts=("call", "texting")), {}, None
    monkeypatch.setattr(hybrid, "crops", lambda g, lm: ((None, None, None, None), None, 0.0))
    out = h.feed(0.0, np.zeros((4, 4), np.uint8), np.zeros((478, 2)))
    assert out["action"] == "other" and out["p"] == 0.08
    assert not stream.occludes_eyes({"action": "eating", "p": 0.99})
