from dms_fusion import AlertPattern as P
from dms_fusion import FusionDecision as D
from dms_fusion.policy import AlertPolicy

NONE, BEEP, REP, CONT, MAX = (D(P.NONE), D(P.SHORT_BEEP, ["face distracted"]),
                              D(P.REPEATED, ["face drowsy"]), D(P.CONTINUOUS, ["phone call"]),
                              D(P.MAX, ["driver not responding"]))


def run(policy: AlertPolicy, steps: list[tuple[float, D]]) -> list[tuple[P, int]]:
    return [(o.decision.pattern, o.episode) for o in (policy.update(t, d) for t, d in steps)]


def test_flicker_is_one_episode_held_until_clear_for_3s():
    # real log: drowsy -> none -> drowsy every ~1 s
    out = run(AlertPolicy(), [(0, REP), (1, NONE), (1.8, REP), (2.5, NONE), (3.2, REP), (5, NONE),
                              (7.9, NONE), (8.3, NONE)])
    assert [p for p, _ in out] == [P.REPEATED] * 6 + [P.NONE] * 2  # clear 4.7 s after last seen
    assert {e for _, e in out} == {1}


def test_cooldown_blocks_an_immediate_restart_of_the_same_alert():
    p = AlertPolicy()
    run(p, [(0, BEEP), (3.1, NONE)])
    assert p.update(5, BEEP).decision.pattern is P.NONE  # 10 s cooldown for beeps
    assert p.update(13.2, BEEP).decision.pattern is P.SHORT_BEEP
    assert p.episode == 2


def test_escalation_preempts_and_lower_never_interrupts_higher():
    out = run(AlertPolicy(), [(0, REP), (1, CONT), (2, REP), (3, BEEP), (4, CONT)])
    assert [p for p, _ in out] == [P.REPEATED, P.CONTINUOUS, P.CONTINUOUS, P.CONTINUOUS,
                                   P.CONTINUOUS]
    assert [e for _, e in out] == [1, 2, 2, 2, 2]


def test_de_escalation_waits_for_hold_then_continues_lower_alert():
    out = run(AlertPolicy(), [(0, MAX), (1, REP), (2.9, REP), (3.1, REP)])
    assert [p for p, _ in out] == [P.MAX, P.MAX, P.MAX, P.REPEATED]  # MAX last seen at 0 s


def test_ack_flapping_from_the_real_watch_test_is_absorbed():
    # MAX <-> repeated every 0.3 s (before the emergency fix) must stay one MAX episode
    steps = [(75.8 + i * 0.3, MAX if i % 2 == 0 else REP) for i in range(10)]
    out = run(AlertPolicy(), steps)
    assert {p for p, _ in out} == {P.MAX}
    assert {e for _, e in out} == {1}


def test_emergency_flag_at_max_is_a_new_episode():
    p = AlertPolicy()
    p.update(0, MAX)
    out = p.update(20, D(P.MAX, ["emergency: unresponsive"], emergency="unresponsive"))
    assert out.decision.emergency == "unresponsive" and out.episode == 2


def test_emergency_is_never_cooled_down():
    p = AlertPolicy()
    run(p, [(0, MAX), (3.1, NONE)])
    assert p.update(3.2, MAX).decision.pattern is P.MAX


def test_calibration_silences_everything():
    p = AlertPolicy()
    p.update(0, REP)
    assert p.update(1, MAX, calibrating=True).decision.pattern is P.NONE
    assert p.update(2, REP, calibrating=True).decision.pattern is P.NONE
