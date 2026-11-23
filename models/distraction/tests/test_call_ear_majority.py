"""Call alert: sustained ear phone must fire even when action tops as drinking."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hybrid_alerts import CLASSES, AlertLogic  # noqa: E402


def probs(top: str, p: float = 0.9) -> np.ndarray:
    out = np.full(len(CLASSES), (1.0 - p) / (len(CLASSES) - 1))
    out[CLASSES.index(top)] = p
    return out


def test_call_from_ear_majority_while_action_says_drinking():
    logic = AlertLogic(alerts=("call",), use_talk=False, phone_p=0.5)
    # 2.0 s window needs span >= 1.6 s; 21 samples at 0.1 s.
    for i in range(21):
        state, onsets = logic.update(i * 0.1, probs("drinking"), phone=0.95, lip=0.02)
    assert state["call"] is True
    assert "call" in onsets or logic.on["call"]


def test_no_call_when_ear_never_scored():
    logic = AlertLogic(alerts=("call",), use_talk=False, phone_p=0.5)
    for i in range(21):
        state, _ = logic.update(i * 0.1, probs("drinking"), phone=None, lip=0.02)
    assert state["call"] is False


def test_no_call_when_ear_low():
    logic = AlertLogic(alerts=("call",), use_talk=False, phone_p=0.5)
    for i in range(21):
        state, _ = logic.update(i * 0.1, probs("drinking"), phone=0.2, lip=0.02)
    assert state["call"] is False


def test_original_call_majority_still_works():
    logic = AlertLogic(alerts=("call",), use_talk=False, phone_p=0.5)
    for i in range(21):
        state, _ = logic.update(i * 0.1, probs("call"), phone=0.8, lip=0.02)
    assert state["call"] is True
