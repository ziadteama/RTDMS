"""Rule engine on synthetic landmarks and boxes.

Face: centre (320, 260), width 120 px. Driver's right ear (234) at x=260 (image-left), left ear
(454) at x=380 (image-right), chin y=326, mouth centre ~(320, 294).
"""

import math

import numpy as np
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


def run_hand(e, seconds, hand_fn, t0=0.0, fps=30, person_fn=None, clf_fn=None, extra=()):
    """Feed frames; hand_fn(t) -> hand box tuple or None. Returns the last FrameEvidence."""
    ev = None
    for i in range(int(seconds * fps)):
        t = t0 + i / fps
        h = hand_fn(t)
        dets = ([det("hand", *h)] if h else []) + list(extra)
        ev = e.evaluate(t, make_face(), dets, person=person_fn(t) if person_fn else None,
                        clf=clf_fn(t) if clf_fn else None)
    return ev


RIGHT_EAR_HAND = (215, 270, 50, 50)  # centred in the near (driver's right) ear zone
LEFT_EAR_HAND = (410, 270, 50, 50)


def dwell(ev, ear="phone_right_ear", variant="hands"):
    return ev.ears[ear].variants[variant]


def test_hand_at_either_ear_builds_dwell():
    for ear, box in (("phone_right_ear", RIGHT_EAR_HAND), ("phone_left_ear", LEFT_EAR_HAND)):
        ev = run_hand(engine(), 3.5, lambda t, box=box: box)
        d, seen = dwell(ev, ear)
        assert d >= 3.0 and not seen, ear


def test_scratching_under_dwell_never_reaches_warning():
    e = engine()
    ev = run_hand(e, 1.5, lambda t: RIGHT_EAR_HAND)
    assert dwell(ev)[0] < 3.0
    ev = run_hand(e, 2.0, lambda t: None, t0=1.5)  # hand away > gap: episode ends
    assert dwell(ev)[0] == 0.0
    ev = run_hand(e, 1.5, lambda t: RIGHT_EAR_HAND, t0=3.5)  # scratch again: counts from 0
    assert dwell(ev)[0] < 1.6


def test_short_detection_misses_do_not_reset_the_episode():
    # hand box missing for 0.4 s every second (< gap_s 0.7)
    ev = run_hand(engine(), 4.0, lambda t: RIGHT_EAR_HAND if (t % 1.0) < 0.6 else None)
    assert dwell(ev)[0] >= 3.0


def test_hand_above_the_eye_line_is_not_at_the_ear():
    # temple / top of the head: the elbow-on-door posture
    ev = run_hand(engine(), 4.0, lambda t: (215, 200, 50, 40))
    assert dwell(ev, "phone_right_ear")[0] == 0.0


def test_hand_holding_cup_at_ear_height_is_not_a_call():
    cup = det("drink", 410, 275, 40, 50)
    ev = run_hand(engine(), 4.0, lambda t: LEFT_EAR_HAND, extra=[cup])
    assert dwell(ev, "phone_left_ear")[0] == 0.0


def test_hand_on_chin_is_not_at_an_ear():
    ev = run_hand(engine(), 4.0, lambda t: (320, 335, 70, 60))
    assert dwell(ev, "phone_right_ear")[0] == 0.0 and dwell(ev, "phone_left_ear")[0] == 0.0


def person(wrist, elbow=None, shoulder=(220, 420), vis=0.9):
    from rtdms_distraction.pose import Person
    from rtdms_distraction.types import Box

    k = np.zeros((17, 3))
    # driver's right arm = COCO right (6 shoulder, 8 elbow, 10 wrist)
    k[6] = (*shoulder, vis)
    k[10] = (*wrist, vis)
    if elbow is not None:
        k[8] = (*elbow, vis)
    return Person(Box(100, 100, 540, 640), 0.9, k)


def test_pose_wrist_rule():
    e = engine()
    ear = (260, 260)  # landmark 234
    cases = {
        "raised elbow": (person((ear[0] - 10, ear[1] + 30), elbow=(200, 380)), True),
        "elbow hanging by the body": (person((ear[0] - 10, ear[1] + 30), elbow=(230, 600)),
                                      False),
        "wrist above the eye line": (person((ear[0], ear[1] - 60), elbow=(200, 380)), False),
        "wrist far from the ear": (person((ear[0] - 120, ear[1] + 30), elbow=(200, 380)), False),
        "elbow out of frame": (person((ear[0] - 10, ear[1] + 30)), True),
    }
    for name, (p, want) in cases.items():
        ev = e.evaluate(0.0, make_face(), [], person=p)
        assert ev.ears["phone_right_ear"].pose is want, name


def test_pose_adds_hand_at_ear_only_in_pose_variants():
    p = person((250, 290), elbow=(200, 380))
    ev = run_hand(engine(), 3.5, lambda t: None, person_fn=lambda t: p)
    assert dwell(ev, variant="hands")[0] == 0.0
    assert dwell(ev, variant="hands+pose")[0] >= 3.0


def test_classifier_phone_upgrades_only_the_clf_variant():
    p = person((250, 290), elbow=(200, 380))
    ev = run_hand(engine(), 3.5, lambda t: RIGHT_EAR_HAND, person_fn=lambda t: p,
                  clf_fn=lambda t: {"phone_right_ear": 0.8, "phone_left_ear": 0.1})
    assert dwell(ev, variant="hands+pose")[1] is False
    assert dwell(ev, variant="hands+pose+clf")[1] is True
    ev = run_hand(engine(), 3.5, lambda t: RIGHT_EAR_HAND,
                  clf_fn=lambda t: {"phone_right_ear": 0.4, "phone_left_ear": 0.1})
    assert dwell(ev, variant="hands+pose+clf")[1] is False  # below classifier_phone 0.6


def test_phone_box_in_zone_during_episode_marks_phone_seen():
    phone = det("phone", 215, 265, 35, 70)
    ev = run_hand(engine(), 3.5, lambda t: RIGHT_EAR_HAND, extra=[phone])
    assert dwell(ev)[1] is True


def test_driver_side_sets_which_ear_zone_reaches_behind_the_head():
    lhd = engine("right").evaluate(0.0, make_face(), [])
    rhd = engine("left").evaluate(0.0, make_face(), [])
    # far ear zone extends inward past its landmark (inward 0.35 fw = 42 px)
    assert lhd.zones["phone_left_ear"].x1 <= 380 - 42 + 1
    assert rhd.zones["phone_right_ear"].x2 >= 260 + 42 - 1


def test_face_lost_reuses_last_face_geometry_for_detector_evidence():
    e = engine()
    e.evaluate(0.0, make_face(), [])
    cup = det("drink", 320, 300, 50, 70)
    ev = e.evaluate(2.0, None, [cup])  # face hidden behind the cup
    assert ev.stale_face and active(ev, "drinking") is True
    assert active(ev, "eating") is None and active(ev, "phone_in_hand") is None
    ev = e.evaluate(6.0, None, [cup])  # beyond face_geometry_hold_s (5 s)
    assert not ev.stale_face and active(ev, "drinking") is None


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


def test_mouth_classifier_drink_and_food_evidence():
    e = engine()
    ev = e.evaluate(0.0, make_face(), [], mouth_p={"drink": 0.8, "food": 0.1, "none": 0.1})
    assert active(ev, "drinking") is True and "mouth classifier" in ev.behaviours["drinking"].why
    ev = e.evaluate(0.1, make_face(), [], mouth_p={"drink": 0.4, "food": 0.1, "none": 0.5})
    assert active(ev, "drinking") is False
    # P(food) marks food at the mouth; chewing still decides eating
    e2 = engine()
    ev = run_mouth(e2, 0.1, chew, lambda t: 0.03)
    e2.evaluate(0.2, make_face(), [], mouth_p={"drink": 0.0, "food": 0.9, "none": 0.1})
    ev = run_mouth(e2, 4.0, chew, lambda t: 0.03)
    assert e2._last_food_t == 0.2


def test_mouth_classifier_drink_counts_while_the_cup_hides_the_face():
    e = engine()
    e.evaluate(0.0, make_face(), [])
    ev = e.evaluate(0.5, None, [], mouth_p={"drink": 0.9, "food": 0.0, "none": 0.1})
    assert ev.stale_face and active(ev, "drinking") is True
    assert "(last face)" in ev.behaviours["drinking"].why
