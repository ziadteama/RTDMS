from dms_fusion import AlertPattern, decide
from dms_fusion.emergency import EmergencyInputs as In
from dms_fusion.emergency import EmergencyMonitor, EmergencyStage

CLOSED = 9000.0  # ms, past the 8 s trigger


def run(m: EmergencyMonitor, steps: list[tuple[float, In]]) -> list[EmergencyStage]:
    return [m.update(t, x).stage for t, x in steps]


def test_short_closure_stays_normal():
    m = EmergencyMonitor()
    assert run(m, [(0, In(closure_ms=3000)), (5, In(closure_ms=7900))]) == [
        EmergencyStage.NORMAL, EmergencyStage.NORMAL]


def test_watch_worn_still_wrist_fires_after_10s():
    m = EmergencyMonitor()
    still = In(closure_ms=CLOSED, worn=True, wrist_still_s=60)
    stages = run(m, [(0, still), (9.9, still), (10.0, still)])
    assert stages == [EmergencyStage.WAITING, EmergencyStage.WAITING, EmergencyStage.EMERGENCY]


def test_no_watch_waits_20s():
    m = EmergencyMonitor()
    x = In(closure_ms=CLOSED)
    assert run(m, [(0, x), (19, x), (20, x)])[-2:] == [
        EmergencyStage.WAITING, EmergencyStage.EMERGENCY]


def test_abnormal_hr_at_good_quality_shortens_wait():
    m = EmergencyMonitor()
    x = In(closure_ms=CLOSED, worn=True, wrist_still_s=60, hr_bpm=35, hr_quality="good")
    assert run(m, [(0, x), (5, x)]) == [EmergencyStage.WAITING, EmergencyStage.EMERGENCY]


def test_abnormal_hr_at_bad_quality_is_ignored():
    m = EmergencyMonitor()
    x = In(closure_ms=CLOSED, worn=True, wrist_still_s=60, hr_bpm=35, hr_quality="bad")
    assert run(m, [(0, x), (5, x)]) == [EmergencyStage.WAITING, EmergencyStage.WAITING]


def test_missing_hr_never_blocks():
    m = EmergencyMonitor()
    x = In(closure_ms=CLOSED, worn=True, wrist_still_s=60, hr_bpm=None, hr_quality=None)
    assert run(m, [(0, x), (10, x)])[-1] is EmergencyStage.EMERGENCY


def test_ack_eyes_open_or_wrist_move_reset():
    for response in (In(closure_ms=CLOSED, ack=True), In(closure_ms=0),
                     In(closure_ms=CLOSED, worn=True, wrist_still_s=1)):
        m = EmergencyMonitor()
        start = In(closure_ms=CLOSED, worn=True, wrist_still_s=60)
        assert run(m, [(0, start), (4, response)]) == [
            EmergencyStage.WAITING, EmergencyStage.NORMAL]


def test_face_lost_is_not_a_response():
    m = EmergencyMonitor()
    assert run(m, [(0, In(closure_ms=CLOSED)), (20, In(closure_ms=None))])[-1] is (
        EmergencyStage.EMERGENCY)


def test_ack_before_trigger_keeps_normal():
    m = EmergencyMonitor()
    assert m.update(0, In(closure_ms=CLOSED, ack=True)).stage is EmergencyStage.NORMAL


def test_decide_maps_stages():
    m = EmergencyMonitor()
    waiting = m.update(0, In(closure_ms=CLOSED))
    d = decide(face={"state": "drowsy"}, emergency=waiting)
    assert d.pattern is AlertPattern.MAX and d.emergency is None
    assert d.reasons[0] == "driver not responding"
    fired = m.update(20, In(closure_ms=CLOSED))
    d = decide(face={"state": "drowsy"}, emergency=fired)
    assert d.pattern is AlertPattern.MAX and d.emergency == "unresponsive"
