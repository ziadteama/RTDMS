"""Simple mode: phone box >= 1 s -> ALERT; drink / food over the lower face -> ALERT."""

import numpy as np
import pytest

from rtdms_distraction.config import SimpleRulesConfig, load_rules_config
from rtdms_distraction.rules import face_scale
from rtdms_distraction.simple_rules import SimpleRules, lower_face
from rtdms_distraction.types import Box, Detection, FaceObservation

FPS = 30


def face(cx=320.0, cy=200.0, fw=100.0):
    lm = np.zeros((478, 2))
    lm[:] = (cx, cy)
    lm[234] = (cx - fw / 2, cy)  # driver's right ear
    lm[454] = (cx + fw / 2, cy)
    lm[10] = (cx, cy - 0.6 * fw)  # forehead
    lm[152] = (cx, cy + 0.6 * fw)  # chin
    lm[1] = (cx, cy + 0.05 * fw)  # nose tip
    return FaceObservation(lm, 0.0, 0.0, 0.0, "none", 0.0, "geometric", 0.0)


def run(rules, seconds, dets, f=None, t0=0.0):
    out = None
    for i in range(int(seconds * FPS)):
        out = rules.update(t0 + i / FPS, f, dets)
    return out, t0 + int(seconds * FPS) / FPS


def test_lower_face_box():
    f = face()
    fw = face_scale(f)  # the rules' face-width unit (robust to head turns)
    z = lower_face(f, SimpleRulesConfig())
    assert (z.x1, z.x2) == pytest.approx((270 - 0.25 * fw, 370 + 0.25 * fw))
    assert (z.y1, z.y2) == pytest.approx((205.0, 260 + 0.35 * fw))  # nose tip .. chin + 0.35 fw


def test_phone_needs_about_a_second():
    r = SimpleRules(SimpleRulesConfig())
    phone = [Detection("phone", 0.7, Box(100, 100, 140, 180))]
    out, t = run(r, 0.4, phone, face())
    assert out["phone"]["level"] == "none"
    out, t = run(r, 0.8, phone, face(), t)
    assert out["phone"]["level"] == "alert"
    out, _ = run(r, 1.5, [], face(), t)
    assert out["phone"]["level"] == "none"


def test_phone_alerts_without_a_face():
    r = SimpleRules(SimpleRulesConfig())
    out, _ = run(r, 1.5, [Detection("phone", 0.5, Box(0, 0, 10, 10))], None)
    assert out["phone"]["level"] == "alert"


def test_drink_only_at_the_lower_face():
    r = SimpleRules(SimpleRulesConfig())
    lap = [Detection("drink", 0.8, Box(300, 400, 340, 470))]  # cup in the lap
    out, t = run(r, 1.0, lap, face())
    assert out["drinking"]["level"] == "none"
    lips = [Detection("drink", 0.8, Box(300, 250, 340, 320))]
    out, _ = run(r, 1.0, lips, face(), t)
    assert out["drinking"]["level"] == "alert" and out["eating"]["level"] == "none"


def test_cup_hiding_the_face_still_counts():
    r = SimpleRules(SimpleRulesConfig())
    run(r, 0.2, [], face())
    out, _ = run(r, 0.8, [Detection("drink", 0.8, Box(300, 250, 340, 320))], None, 0.2)
    assert out["drinking"]["level"] == "alert"  # last face reused for face_hold_s


def test_food_at_the_lower_face():
    r = SimpleRules(SimpleRulesConfig())
    out, _ = run(r, 1.0, [Detection("food", 0.6, Box(330, 270, 360, 300))], face())
    assert out["eating"]["level"] == "alert"


def test_rules_yaml_mode():
    assert load_rules_config().mode in ("full", "simple")
