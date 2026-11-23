"""max <-> drowsy loop regressions (fusion emergency monitor)."""

from __future__ import annotations

from dms_fusion import AlertPattern, decide
from dms_fusion.emergency import EmergencyInputs, EmergencyMonitor, EmergencyStage


def test_wrist_twitch_during_wait_still_reaches_unresponsive():
    m = EmergencyMonitor()
    closed = EmergencyInputs(closure_ms=12_000, worn=True, wrist_still_s=60)
    twitch = EmergencyInputs(closure_ms=13_000, worn=True, wrist_still_s=0.2)
    t = 0.0
    stage = EmergencyStage.NORMAL
    for _ in range(6):
        stage = m.update(t, closed).stage
        t += 4.0
        stage = m.update(t, twitch).stage
        t += 1.0
    assert stage is EmergencyStage.EMERGENCY


def test_blink_during_wait_keeps_max_not_drowsy_flip():
    m = EmergencyMonitor()
    assert m.update(0.0, EmergencyInputs(closure_ms=10_000)).stage is EmergencyStage.WAITING
    d_max = decide(face={"state": "drowsy"}, emergency=m.update(1.0, EmergencyInputs(closure_ms=0)))
    assert d_max.pattern is AlertPattern.MAX and d_max.emergency is None
    d_still = decide(
        face={"state": "drowsy"},
        emergency=m.update(1.4, EmergencyInputs(closure_ms=11_000)),
    )
    assert d_still.pattern is AlertPattern.MAX


def test_clean_hold_fires_unresponsive_after_20s_without_watch():
    m = EmergencyMonitor()
    x = EmergencyInputs(closure_ms=20_000)
    assert m.update(0.0, x).stage is EmergencyStage.WAITING
    assert m.update(19.0, x).stage is EmergencyStage.WAITING
    fired = m.update(20.0, x)
    assert fired.stage is EmergencyStage.EMERGENCY
    d = decide(face={"state": "drowsy"}, emergency=fired)
    assert d.pattern is AlertPattern.MAX and d.emergency == "unresponsive"
