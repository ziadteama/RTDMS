"""Rule engine on synthetic landmarks and boxes.

Face: centre (320, 260), width 120 px. Driver's right ear (234) at x=260 (image-left), left ear
(454) at x=380 (image-right), chin y=326, mouth centre ~(320, 294).
"""

import math

import pytest
from helpers import det, engine, make_face

from rtdms_distraction.config import RulesConfig


def active(ev, name):
    return ev.behaviours[name].active


# --------------------------------------------------------------------------- ears


def test_phone_at_right_ear_lhd():
    e = engine("right")
    ev = e.evaluate(0.0, make_face(), [det("phone", 215, 265, 35, 70)])
    assert active(ev, "phone_right_ear") is True
    assert active(ev, "phone_left_ear") is False
    assert active(ev, "phone_in_hand") is False  # a phone at the ear is not also in-hand


def test_phone_at_left_ear_lhd_full_and_partial():
    for box in [(420, 265, 35, 70), (350, 260, 20, 50)]:  # visible / mostly hidden by the head
        ev = engine("right").evaluate(0.0, make_face(), [det("phone", *box)])
        assert active(ev, "phone_left_ear") is True, box
        assert active(ev, "phone_right_ear") is False


def test_hand_only_counts_at_far_ear_only():
    hand = det("hand", 410, 250, 60, 70, conf=0.9)
    ev = engine("right").evaluate(0.0, make_face(), [hand])
    assert active(ev, "phone_left_ear") is True
    assert ev.behaviours["phone_left_ear"].confidence == pytest.approx(0.6 * 0.9)

    near_hand = det("hand", 215, 250, 60, 70)
    ev = engine("right").evaluate(0.0, make_face(), [near_hand])
    assert active(ev, "phone_right_ear") is False  # near ear is visible: needs the phone itself


def test_driver_side_left_swaps_near_and_far():
    # RHD: camera to the driver's left; the driver's RIGHT ear (image-left) is now the far one.
    e = engine("left")
    ev = e.evaluate(0.0, make_face(), [det("hand", 225, 250, 60, 70)])
    assert active(ev, "phone_right_ear") is True
    ev = engine("left").evaluate(0.0, make_face(), [det("hand", 410, 250, 60, 70)])
    assert active(ev, "phone_left_ear") is False


def test_hand_holding_cup_at_mouth_is_not_a_far_ear_call():
    hand = det("hand", 345, 300, 60, 60)
    cup = det("drink", 335, 295, 40, 60)
    ev = engine("right").evaluate(0.0, make_face(), [hand, cup])
    assert active(ev, "phone_left_ear") is False
    assert active(ev, "drinking") is True


def test_hand_on_chin_is_not_a_far_ear_call():
    ev = engine("right").evaluate(0.0, make_face(), [det("hand", 320, 330, 70, 60)])
    assert active(ev, "phone_left_ear") is False


def test_hand_only_can_be_disabled():
    cfg = RulesConfig()
    cfg.ears.far.hand_only = False
    e = engine("right", cfg=cfg)
    ev = e.evaluate(0.0, make_face(), [det("hand", 410, 250, 60, 70)])
    assert active(ev, "phone_left_ear") is False


def test_ear_zones_scale_with_face_size():
    # Same layout, face twice as large and moved: still at the ear.
    face = make_face(cx=300, cy=300, fw=240)
    ev = engine("right").evaluate(0.0, face, [det("phone", 300 - 120 - 45, 310, 70, 140)])
    assert active(ev, "phone_right_ear") is True


# --------------------------------------------------------------------------- phone in hand


def test_phone_in_hand_below_face_next_to_hand():
    ev = engine().evaluate(0.0, make_face(), [det("phone", 330, 450, 40, 70),
                                              det("hand", 335, 470, 70, 70)])
    assert active(ev, "phone_in_hand") is True


def test_phone_without_hand_nearby_is_ignored_when_hands_are_on():
    ev = engine().evaluate(0.0, make_face(), [det("phone", 330, 450, 40, 70),
                                              det("hand", 80, 600, 60, 60)])
    assert active(ev, "phone_in_hand") is False


def test_phone_in_hand_without_hand_source():
    ev = engine(hands=False).evaluate(0.0, make_face(), [det("phone", 330, 450, 40, 70)])
    assert active(ev, "phone_in_hand") is True


def test_phone_in_holder_zone_is_ignored():
    cfg = RulesConfig()
    cfg.phone_in_hand.holder_zones = [[0.0, 0.6, 0.3, 0.4]]  # x 0-192, y 384-640
    e = engine(hands=False, cfg=cfg)
    ev = e.evaluate(0.0, make_face(), [det("phone", 100, 500, 40, 70)])
    assert active(ev, "phone_in_hand") is False


def test_phone_above_chin_is_not_in_hand():
    ev = engine(hands=False).evaluate(0.0, make_face(), [det("phone", 320, 240, 40, 60)])
    assert active(ev, "phone_in_hand") is False


def test_head_down_needs_baseline_then_counts_time():
    e = engine(baseline_s=1.0, min_samples=5)
    for i in range(40):  # 1.3 s of neutral pose -> baseline 0
        ev = e.evaluate(i / 30, make_face(pitch=0.0), [])
    assert e.baseline.ready and ev.head_down is False
    t = 2.0
    ev = e.evaluate(t, make_face(pitch=20.0), [])
    assert ev.head_down is True and ev.head_down_s == 0.0
    ev = e.evaluate(t + 2.5, make_face(pitch=20.0), [])
    assert ev.head_down_s == pytest.approx(2.5)
    ev = e.evaluate(t + 2.6, make_face(pitch=0.0), [])
    assert ev.head_down is False and ev.head_down_s == 0.0


def test_gaze_down_alone_counts_as_head_down():
    e = engine()
    e.evaluate(0.0, make_face(gaze=0.0), [])
    ev = e.evaluate(0.1, make_face(gaze=0.4), [])
    assert ev.head_down is True


# --------------------------------------------------------------------------- drinking


def test_drink_at_mouth():
    ev = engine().evaluate(0.0, make_face(), [det("drink", 320, 300, 50, 70)])
    assert active(ev, "drinking") is True


def test_drink_on_lap_is_not_drinking():
    ev = engine().evaluate(0.0, make_face(), [det("drink", 320, 520, 50, 70)])
    assert active(ev, "drinking") is False


def test_pitch_up_raises_drinking_confidence():
    e = engine()
    e.evaluate(0.0, make_face(pitch=0.0), [])  # baseline 0 (duration 0)
    cup = det("drink", 320, 300, 50, 70, conf=0.6)
    level = e.evaluate(0.1, make_face(pitch=0.0), [cup]).behaviours["drinking"].confidence
    tilted = e.evaluate(0.2, make_face(pitch=-15.0), [cup]).behaviours["drinking"].confidence
    assert level == pytest.approx(0.6)
    assert tilted == pytest.approx(0.75)


# --------------------------------------------------------------------------- eating


def run_mouth(e, seconds, jaw_fn, lip_fn, food_at=None, fps=30):
    ev = None
    for i in range(int(seconds * fps)):
        t = i / fps
        dets = [det("food", 320, 300, 40, 40)] if food_at is not None and \
            abs(t - food_at) < 0.5 else []
        ev = e.evaluate(t, make_face(jaw=jaw_fn(t), lip=lip_fn(t)), dets)
    return ev


def chew(t):
    return 0.15 + 0.08 * math.sin(2 * math.pi * 1.5 * t)


def test_food_then_chewing_is_eating():
    ev = run_mouth(engine(), 4.0, chew, lambda t: 0.03, food_at=0.3)
    assert ev.chewing.chewing, ev.chewing.why
    assert active(ev, "eating") is True


def test_chewing_without_food_is_not_eating():
    ev = run_mouth(engine(), 4.0, chew, lambda t: 0.03)
    assert ev.chewing.chewing
    assert active(ev, "eating") is False


def test_food_memory_expires():
    ev = run_mouth(engine(), 7.0, chew, lambda t: 0.03, food_at=0.3)
    assert active(ev, "eating") is False


def test_talking_with_food_nearby_is_not_eating():
    # Syllable-rate jaw movement (~4.5 Hz) with the lips apart most of the time.
    def talk_jaw(t):
        return 0.2 + 0.1 * math.sin(2 * math.pi * 4.5 * t) + 0.03 * math.sin(2 * math.pi * 2.9 * t)

    def talk_lip(t):
        return 0.25 if math.sin(2 * math.pi * 4.5 * t) > -0.6 else 0.05

    ev = run_mouth(engine(), 4.0, talk_jaw, talk_lip, food_at=0.3)
    assert not ev.chewing.chewing
    assert active(ev, "eating") is False


def test_singing_is_not_chewing():
    ev = run_mouth(engine(), 4.0, lambda t: 0.5 + 0.05 * math.sin(2 * math.pi * 1.2 * t),
                   lambda t: 0.45, food_at=0.3)
    assert not ev.chewing.chewing
    assert "lips open" in ev.chewing.why


def test_still_mouth_is_not_chewing():
    ev = run_mouth(engine(), 4.0, lambda t: 0.1, lambda t: 0.02, food_at=0.3)
    assert not ev.chewing.chewing


def test_geometric_jaw_source_uses_its_own_amplitude_threshold():
    e = engine()
    for i in range(120):
        t = i / 30
        jaw = 0.62 + 0.02 * math.sin(2 * math.pi * 1.4 * t)  # chin-nose distance in fw
        e.evaluate(t, make_face(jaw=jaw, lip=0.03, jaw_source="geometric"), [])
    assert e.chewing.analyze().chewing


# --------------------------------------------------------------------------- face lost


def test_no_face_gives_unknown_not_negative():
    ev = engine().evaluate(0.0, None, [det("phone", 215, 265, 35, 70)])
    assert all(v.active is None for v in ev.behaviours.values())
