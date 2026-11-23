"""Hand / phone / cup at the face must not count as closed eyes (stream.py occlusion gate)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stream  # noqa: E402


def test_hand_phone_cup_at_face_hide_the_eyes():
    for action in ("call", "texting", "drinking", "eating", "hand_on_face"):
        assert stream.occludes_eyes({"action": action, "p": 0.8})


def test_normal_low_confidence_or_no_face_do_not():
    assert not stream.occludes_eyes({"action": "normal", "p": 0.99})
    assert not stream.occludes_eyes({"action": "other", "p": 0.99})
    assert not stream.occludes_eyes({"action": "drinking", "p": 0.3})
    assert not stream.occludes_eyes({"action": None, "p": None})  # no face
    assert not stream.occludes_eyes(None)  # --hybrid off
