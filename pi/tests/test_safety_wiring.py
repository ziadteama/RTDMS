from __future__ import annotations

from pathlib import Path

from conftest import Clock
from dms_fusion import AlertPattern

from rtdms_pi.buzzer import PatternPlayer, RecordingBuzzer
from rtdms_pi.clock import PhoneClock
from rtdms_pi.payloads import alert_payload
from rtdms_pi.runtime import Runtime
from rtdms_pi.safety import Safety
from rtdms_pi.sources import FrameResult, NullPhysioSource, ScriptedFrameSource
from rtdms_pi.state import FaceReport, PhysioReport, RuntimeState

MODEL = Path(__file__).resolve().parents[2] / "models/physiology/models/hr_shadow_mpddf_v1.json"


class Physio:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.raw: dict[str, object] = {}

    def latest(self) -> PhysioReport | None:
        return PhysioReport(self.raw, self.clock()) if self.raw else None


def make(clock: Clock, physio: object | None = None, model: Path = MODEL) -> Runtime:
    return Runtime(
        ScriptedFrameSource([]),
        physio or NullPhysioSource(),  # type: ignore[arg-type]
        PatternPlayer(RecordingBuzzer(), autostart=False),
        RuntimeState(clock=clock),
        clock,
        safety=Safety(model),
    )


def eyes(rt: Runtime, clock: Clock, closure_ms: float, state: str = "drowsy") -> None:
    face = FaceReport(state=state, face=True, closure_ms=closure_ms)
    rt.on_frame(FrameResult(face, None, 15, None, True, clock()))


def test_unresponsive_without_watch_reaches_alert_payload(clock: Clock) -> None:
    rt = make(clock)
    eyes(rt, clock, 9000)
    d = rt.state.snapshot().decision
    assert d.pattern is AlertPattern.MAX and d.reasons[0] == "driver not responding"
    assert "emergency" not in alert_payload(d, clock(), PhoneClock())
    clock.advance(20)
    eyes(rt, clock, 29000)
    d = rt.state.snapshot().decision
    assert d.emergency == "unresponsive"
    assert alert_payload(d, clock(), PhoneClock())["emergency"] == "unresponsive"
    rt.stop()


def test_watch_ack_resets_the_wait(clock: Clock) -> None:
    physio = Physio(clock)
    physio.raw = {"watch_connected": True, "worn": True, "wrist_still_s": 60.0,
                  "ack_age_s": None, "quality": "good", "hr_bpm": 70}
    rt = make(clock, physio)
    eyes(rt, clock, 9000)
    assert rt.state.snapshot().decision.pattern is AlertPattern.MAX
    clock.advance(3)
    physio.raw = {**physio.raw, "ack_age_s": 0.5}
    eyes(rt, clock, 12000)
    assert rt.state.snapshot().decision.pattern is AlertPattern.REPEATED  # face drowsy only
    rt.stop()


def test_break_reminder_reaches_the_decision(clock: Clock) -> None:
    rt = make(clock)
    for _ in range(120):  # one frame a minute for two hours
        eyes(rt, clock, 0, state="alert")
        clock.advance(60)
    eyes(rt, clock, 0, state="alert")
    d = rt.state.snapshot().decision
    assert d.pattern is AlertPattern.SHORT_BEEP and d.reasons == ("break reminder",)
    rt.stop()


def test_shadow_counts_never_change_the_pattern(clock: Clock) -> None:
    physio = Physio(clock)
    physio.raw = {"watch_connected": True, "quality": "good",
                  "hr_delta_bpm": -12.0, "hr_trend_bpm_per_10min": -3.0}
    rt = make(clock, physio)
    eyes(rt, clock, 0, state="alert")
    assert rt.state.snapshot().decision.pattern is AlertPattern.NONE
    eyes(rt, clock, 500, state="drowsy")
    assert rt.state.snapshot().decision.pattern is AlertPattern.REPEATED
    diag = rt.safety.diagnostics() if rt.safety else {}
    assert diag["shadow_agree"] + diag["shadow_disagree"] == 1
    rt.stop()


def test_missing_shadow_model_runs(clock: Clock, tmp_path: Path) -> None:
    rt = make(clock, model=tmp_path / "missing.json")
    assert rt.safety is not None and rt.safety.model is None
    eyes(rt, clock, 0, state="drowsy")
    assert rt.state.snapshot().decision.pattern is AlertPattern.REPEATED
    rt.stop()


def test_face_lost_after_trigger_keeps_counting(clock: Clock) -> None:
    rt = make(clock)
    eyes(rt, clock, 9000)
    clock.advance(20)
    rt.on_frame(FrameResult(FaceReport(state="unavailable", face=False), None, 15, None,
                            True, clock()))  # slumped out of view
    assert rt.state.snapshot().decision.emergency == "unresponsive"
    rt.stop()


def test_emergency_change_notifies_phone_at_once(service, clock: Clock) -> None:
    import json

    from dms_fusion import FusionDecision

    from rtdms_pi.ble.uuids import Char

    service.state.set_decision(FusionDecision(AlertPattern.MAX, ["driver not responding"]))
    service.notifier.step()
    service.state.set_decision(FusionDecision(AlertPattern.MAX, ["emergency: unresponsive"],
                                              emergency="unresponsive"))
    service.notifier.step()  # same pattern, same tick: must still go out now
    alerts = [json.loads(d) for u, d in service.port.notifications if u == Char.ALERT.uuid]
    assert alerts[-1]["emergency"] == "unresponsive"


def calibrating_face(closure_ms: float) -> FaceReport:
    return FaceReport(state="drowsy", face=True, closure_ms=closure_ms,
                      calibration="calibrating", calibration_step="closed")


def test_calibration_silences_alerts_and_resets_the_emergency_count(clock: Clock) -> None:
    rt = make(clock)
    for _ in range(12):  # 12 s with eyes shut on purpose during calibration
        rt.on_frame(FrameResult(calibrating_face(9000), None, 15, None, True, clock()))
        assert rt.state.snapshot().decision.pattern is AlertPattern.NONE
        clock.advance(1)
    eyes(rt, clock, 500)  # calibration over: no SOS carried over from the closed-eye phase
    d = rt.state.snapshot().decision
    assert d.pattern is AlertPattern.REPEATED and d.emergency is None
    rt.stop()


def test_flickering_face_model_gives_one_held_episode(clock: Clock) -> None:
    rt = make(clock)
    seen = []
    for state in ["drowsy", "alert", "drowsy", "alert", "drowsy", "alert", "alert", "alert",
                  "alert", "alert"]:
        eyes(rt, clock, 0, state=state)
        d = rt.state.snapshot().decision
        seen.append((d.pattern, d.episode))
        clock.advance(0.7)
    assert {e for _, e in seen} == {1}
    assert seen[0][0] is AlertPattern.REPEATED and seen[-1][0] is AlertPattern.NONE
    assert all(p is AlertPattern.REPEATED for p, _ in seen[:7])
    rt.stop()
