from dms_fusion import AlertPattern, decide
from dms_fusion.break_reminder import BreakReminder
from dms_fusion.shadow import ShadowCounts, ShadowTracker

R, N = AlertPattern.REPEATED, AlertPattern.NONE


def test_shadow_counts_episodes_not_frames():
    s = ShadowTracker()
    for pattern, score in [(R, 0.9), (R, 0.9), (N, 0.2), (R, 0.3), (N, 0.8), (N, 0.9), (N, None)]:
        s.observe(pattern, score)
    assert s.counts == ShadowCounts(agree=1, disagree=1, shadow_only=1)


def test_shadow_skips_missing_score():
    s = ShadowTracker()
    s.observe(R, None)
    assert s.counts == ShadowCounts()


def drive(b: BreakReminder, start: float, end: float, step: float = 60.0) -> None:
    t = start
    while t < end:
        b.due(t, True)
        t += step


def test_break_reminder_pulses_at_two_hours_then_every_30_min():
    b = BreakReminder()
    drive(b, 0, 2 * 3600 - 60)
    assert not b.due(2 * 3600 - 1, True)
    assert b.due(2 * 3600 + 1, True)
    assert not b.due(2 * 3600 + 10, True)
    drive(b, 2 * 3600 + 60, 2.5 * 3600 - 60)
    assert b.due(2.5 * 3600 + 1, True)


def test_break_reminder_resets_after_driver_away():
    b = BreakReminder()
    drive(b, 0, 3600)
    assert b.due(3600 + 11 * 60, False) is False  # away 11 min: drive over
    drive(b, 3600 + 12 * 60, 3600 + 12 * 60 + 2 * 3600 - 60)
    assert not b.due(3600 + 12 * 60 + 2 * 3600 - 5, True)
    assert b.driven_s(3600 + 12 * 60 + 2 * 3600 - 5) == 2 * 3600 - 5


def test_break_reminder_only_beeps_when_quiet():
    assert decide(break_due=True).pattern is AlertPattern.SHORT_BEEP
    assert decide(face={"state": "drowsy"}, break_due=True).reasons == ["face drowsy"]
