from __future__ import annotations

from unittest.mock import patch

import pytest
from conftest import Clock
from dms_fusion import AlertPattern, decide

from rtdms_pi.buzzer import PatternPlayer, RecordingBuzzer
from rtdms_pi.payloads import status_payload
from rtdms_pi.runtime import Runtime
from rtdms_pi.sources import (
    CAMERA_ARGS,
    FrameResult,
    NullPhysioSource,
    ScriptedFrameSource,
    map_status,
)
from rtdms_pi.state import FaceReport, PhoneReport, PhysioReport, RuntimeState


def test_scripted_ladder_and_stale(clock: Clock) -> None:
    state = RuntimeState(clock=clock)
    backend = RecordingBuzzer()
    player = PatternPlayer(backend, clock=clock, autostart=False)
    frames = [
        FrameResult(FaceReport(state=s, face=True), p, 15, None, True, clock())
        for s, p in [
            ("alert", None),
            ("distracted", None),
            ("drowsy", None),
            ("alert", PhoneReport(phone_score=0.8, sustained_phone_ms=500)),
        ]
    ]
    source = ScriptedFrameSource(frames)
    runtime = Runtime(source, NullPhysioSource(), player, state, clock)
    seen: list[AlertPattern] = []

    def observe(frame: FrameResult) -> None:
        runtime.on_frame(frame)
        seen.append(state.snapshot().decision.pattern)

    source.start(observe)
    assert seen == [
        AlertPattern.NONE,
        AlertPattern.SHORT_BEEP,
        AlertPattern.REPEATED,
        AlertPattern.CONTINUOUS,
    ]
    clock.advance(2.01)
    runtime.tick()
    assert state.snapshot().decision.pattern == AlertPattern.NONE
    assert status_payload(state.snapshot())["state"] == "unavailable"
    assert state.snapshot().phone is None
    runtime.stop()


def test_physio_none_passed_exactly(clock: Clock) -> None:
    state = RuntimeState(clock=clock)
    runtime = Runtime(
        ScriptedFrameSource([]),
        NullPhysioSource(),
        PatternPlayer(RecordingBuzzer(), autostart=False),
        state,
        clock,
    )
    with patch("rtdms_pi.runtime.decide", wraps=decide) as mocked:
        runtime.tick()
        mocked.assert_called_once_with(face=None, phone=None, physiology=None)
    runtime.stop()


def test_physio_never_escalates_and_expires(clock: Clock) -> None:
    report = PhysioReport({"watch_connected": True, "fatigue_probability": 0.7, "t": 42}, clock())

    class Physio:
        def latest(self) -> PhysioReport:
            return report

    state = RuntimeState(clock=clock)
    runtime = Runtime(
        ScriptedFrameSource([]),
        Physio(),
        PatternPlayer(RecordingBuzzer(), autostart=False),
        state,
        clock,
    )
    runtime.on_frame(
        FrameResult(FaceReport(state="drowsy", face=True), None, 10, None, True, clock())
    )
    assert state.snapshot().decision.pattern == AlertPattern.REPEATED
    clock.advance(11)
    with patch("rtdms_pi.runtime.decide", wraps=decide) as mocked:
        runtime.tick()
        mocked.assert_called_once_with(face=None, phone=None, physiology=None)
    assert state.snapshot().decision.pattern == AlertPattern.NONE
    runtime.stop()


def test_camera_lost_and_missing_face(clock: Clock) -> None:
    state = RuntimeState(clock=clock)
    runtime = Runtime(
        ScriptedFrameSource([]),
        NullPhysioSource(),
        PatternPlayer(RecordingBuzzer(), autostart=False),
        state,
        clock,
    )
    for face, camera_ok in [
        (FaceReport(state="drowsy", face=True), False),
        (FaceReport(state="drowsy", face=False), True),
    ]:
        runtime.on_frame(FrameResult(face, None, 0, None, camera_ok, clock()))
        assert state.snapshot().decision.pattern == AlertPattern.NONE
        assert status_payload(state.snapshot())["state"] == "unavailable"
    runtime.stop()


def test_snapshot_is_deeply_immutable(clock: Clock) -> None:
    raw: dict[str, object] = {"rr_ms": [800], "nested": {"key": [1]}}
    report = PhysioReport(raw, clock())
    raw["rr_ms"] = [900]
    assert report.raw["rr_ms"] == (800,)
    with pytest.raises(TypeError):
        report.raw["new"] = 1  # runtime immutability, tests aren't mypy targets
    state = RuntimeState(clock=clock)
    decision = decide(face={"state": "drowsy"})
    state.set_decision(decision)
    decision.reasons.append("mutated")
    assert state.snapshot().decision.reasons == ("face drowsy",)


def test_map_status_no_guesses() -> None:
    frame = map_status(
        {
            "face": True,
            "fps": 12,
            "hybrid": {"call": True, "texting": False, "p": 0.99, "action": "call"},
        },
        100,
    )
    assert frame.face is not None and frame.face.state == "unavailable"
    assert frame.phone is not None and frame.phone.phone_p == 0.99
    assert frame.phone.phone_score is None and frame.phone.sustained_phone_ms is None
    assert map_status({"face": False, "drowsiness": {"state": "drowsy"}}, 100).face.state == (
        "unavailable"
    )
    assert map_status({}, 100).phone is None


def test_map_status_calibration() -> None:
    # calibrated True -> "ok"
    f1 = map_status(
        {"face": True, "drowsiness": {"face": True, "calibrated": True, "message": "calibrated"}},
        100,
    )
    assert f1.face is not None and f1.face.calibration == "ok" and f1.face.calibrated is True

    # message startswith "calibration failed" -> "failed"
    f2 = map_status(
        {
            "face": True,
            "drowsiness": {
                "face": True,
                "calibrated": False,
                "message": "calibration failed: face moved",
            },
        },
        100,
    )
    assert f2.face is not None and f2.face.calibration == "failed" and f2.face.calibrated is False

    # otherwise None (do not guess "calibrating")
    f3 = map_status(
        {"face": True, "drowsiness": {"face": True, "calibrated": False, "message": "calibrating"}},
        100,
    )
    assert f3.face is not None and f3.face.calibration is None

    f4 = map_status(
        {
            "face": True,
            "drowsiness": {"face": True, "message": "not calibrated: press Calibrate"},
        },
        100,
    )
    assert f4.face is not None and f4.face.calibration is None


def test_threads_stop(clock: Clock) -> None:
    runtime = Runtime(
        ScriptedFrameSource([]),
        NullPhysioSource(),
        PatternPlayer(RecordingBuzzer()),
        RuntimeState(clock=clock),
        clock,
    )
    runtime.start()
    runtime.stop()
    assert runtime._thread is not None and not runtime._thread.is_alive()
    assert not runtime.player._thread.is_alive()


def test_stream_hook_and_shutdown(monkeypatch: pytest.MonkeyPatch, clock: Clock) -> None:
    import threading
    from types import SimpleNamespace

    from rtdms_pi.config import RuntimeConfig
    from rtdms_pi.sources import StreamPipelineSource

    got_frame = threading.Event()
    seen: list[FrameResult] = []
    arguments: list[str] = []

    class Shared:
        def __init__(self) -> None:
            self.cond = threading.Condition()
            self.running = True
            self.status = {"face": False}

    def parse_args(args: list[str]) -> list[str]:
        arguments.extend(args)
        return args

    def pipeline(args: list[str], shared: Shared) -> None:
        with shared.cond:
            shared.status = {
                "face": True,
                "fps": 14,
                "drowsiness": {"state": "drowsy", "face": True},
            }
            while shared.running:
                shared.cond.wait(timeout=1)

    def on_frame(frame: FrameResult) -> None:
        seen.append(frame)
        got_frame.set()

    module = SimpleNamespace(Shared=Shared, pipeline_loop=pipeline, parse_args=parse_args)
    with patch("rtdms_pi.sources.importlib.import_module", return_value=module):
        source = StreamPipelineSource(RuntimeConfig(rotate=90), clock)
        source.start(on_frame)
    try:
        assert got_frame.wait(1)
        assert len(seen) == 1  # ignore the status assignment during Shared construction
        assert isinstance(source.shared, Shared)
        assert seen[0].face.state == "drowsy"
        assert source.camera_ok
        assert arguments == [*CAMERA_ARGS, "--rotate", "90"]  # production flags, start_stream.sh
        clock.advance(3)
        assert not source.camera_ok
    finally:
        source.stop()
    assert not seen[-1].camera_ok
    assert source._thread is not None and not source._thread.is_alive()


def test_watchdog_drops_frozen_camera(clock: Clock) -> None:
    import threading

    state = RuntimeState(clock=clock)
    frame = FrameResult(FaceReport("drowsy", face=True), None, 14, None, True, clock())
    runtime = Runtime(
        ScriptedFrameSource([frame]),
        NullPhysioSource(),
        PatternPlayer(RecordingBuzzer(), autostart=False),
        state,
        clock,
        tick_rate=100,
    )
    dropped = threading.Event()
    original = state.set_decision

    def observe(decision: object) -> None:
        original(decision)
        if decision.pattern == AlertPattern.NONE:
            dropped.set()

    with patch.object(state, "set_decision", side_effect=observe):
        runtime.start()
        try:
            assert state.snapshot().decision.pattern == AlertPattern.REPEATED
            clock.advance(3)
            assert dropped.wait(1)
            assert status_payload(state.snapshot())["state"] == "unavailable"
        finally:
            runtime.stop()
            runtime.stop()  # idempotent cleanup, including hardware ownership


def test_hybrid_call_flag_reaches_fusion(clock: Clock) -> None:
    from rtdms_pi.sources import FrameResult
    from rtdms_pi.state import PhoneReport

    rec = RecordingBuzzer()
    runtime = Runtime(
        ScriptedFrameSource([]),
        NullPhysioSource(),
        PatternPlayer(rec),
        RuntimeState(clock=clock),
        clock,
    )
    runtime.on_frame(FrameResult(None, PhoneReport(call=True), 10.0, None, True, clock()))
    assert runtime.state.snapshot().decision.reasons == ("phone call",)
    runtime.stop()


def test_runtime_start_lifecycle(clock: Clock) -> None:
    runtime = Runtime(
        ScriptedFrameSource([]),
        NullPhysioSource(),
        PatternPlayer(RecordingBuzzer(), autostart=False),
        RuntimeState(clock=clock),
        clock,
    )
    runtime.start()
    with pytest.raises(RuntimeError, match="runtime already started"):
        runtime.start()
    runtime.stop()
    with pytest.raises(RuntimeError, match="runtime is closed"):
        runtime.start()


@pytest.mark.parametrize("calibrated", [True, False, None])
def test_phone_calibration_status(calibrated: bool | None) -> None:
    frame = map_status(
        {"drowsiness": {"calibrated": calibrated, "message": "calibrated (phone)"}}, 1.0
    )
    assert frame.face is not None
    assert frame.face.calibration == "ok"
    assert frame.face.calibrated is calibrated


def test_stream_calibration_effects() -> None:
    from types import SimpleNamespace

    from rtdms_pi.config import RuntimeConfig
    from rtdms_pi.sources import StreamPipelineSource

    profiles = []
    source = StreamPipelineSource(RuntimeConfig())
    source.shared = SimpleNamespace(calibrate=False, submit_phone_calibration=profiles.append)
    source.start_calibration()
    assert source.shared.calibrate is True
    profile = {"source": "phone", "closed_ratio": 0.38}
    source.apply_phone_calibration(profile)
    assert profiles == [profile]
