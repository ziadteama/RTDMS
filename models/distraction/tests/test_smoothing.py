from rtdms_distraction.config import SmoothingConfig
from rtdms_distraction.smoothing import BehaviourSmoother

FPS = 30


def feed(s, t0, seconds, value, conf=0.8):
    st = None
    for i in range(int(seconds * FPS)):
        st = s.update(t0 + i / FPS, value, conf)
    return st, t0 + int(seconds * FPS) / FPS


def test_activates_only_after_enough_history():
    s = BehaviourSmoother(SmoothingConfig(window_s=1.75, min_coverage=0.6))
    st, t = feed(s, 0.0, 0.5, True)
    assert not st.active  # 100% positive but only 0.5 s of window
    st, t = feed(s, t, 0.7, True)
    assert st.active
    assert st.confidence == 0.8


def test_needs_on_ratio():
    s = BehaviourSmoother(SmoothingConfig())
    st = None
    for i in range(120):  # 60% positive: below on_ratio 0.70
        st = s.update(i / FPS, i % 5 < 3)
    assert not st.active


def test_hysteresis_holds_between_thresholds():
    s = BehaviourSmoother(SmoothingConfig())
    _, t = feed(s, 0.0, 2.0, True)
    st = None
    for i in range(90):  # 50% positive: above off_ratio, below on_ratio -> stays on
        st = s.update(t + i / FPS, i % 2 == 0)
    assert st.active
    st, _ = feed(s, t + 3.0, 2.0, False)
    assert not st.active


def test_brief_dropout_does_not_clear():
    s = BehaviourSmoother(SmoothingConfig())
    _, t = feed(s, 0.0, 2.0, True)
    st, t = feed(s, t, 0.3, False)  # a 0.3 s miss inside a 1.75 s window
    assert st.active


def test_none_holds_state_and_does_not_activate():
    s = BehaviourSmoother(SmoothingConfig(face_lost_hold_s=5.0))
    _, t = feed(s, 0.0, 2.0, True)
    st, t = feed(s, t, 3.0, None)
    assert st.active and st.holding
    s2 = BehaviourSmoother(SmoothingConfig())
    st, _ = feed(s2, 0.0, 3.0, None)
    assert not st.active


def test_long_face_loss_clears():
    s = BehaviourSmoother(SmoothingConfig(face_lost_hold_s=2.0))
    _, t = feed(s, 0.0, 2.0, True)
    st, _ = feed(s, t, 2.5, None)
    assert not st.active
