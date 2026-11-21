from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from dms_fusion import AlertPattern

from rtdms_pi.buzzer import PatternPlayer, RecordingBuzzer
from rtdms_pi.detector_gate import apply_settings
from rtdms_pi.payloads import status_payload
from rtdms_pi.runtime import Runtime
from rtdms_pi.settings import SettingsStore
from rtdms_pi.sources import FrameResult, ScriptedFrameSource
from rtdms_pi.state import FaceReport, PhoneReport, RuntimeState, Snapshot


def test_detector_gate_pure() -> None:
    face = {"state": "drowsy"}
    phone = {"call": True}
    physio = {"hr_bpm": 80}

    # Default / None settings -> all unchanged
    assert apply_settings(None, face, phone, physio) == (face, phone, physio)
    assert apply_settings({}, face, phone, physio) == (face, phone, physio)

    # Drowsiness disabled -> blanks face
    assert apply_settings({"detectors": {"drowsiness": False}}, face, phone, physio) == (
        None,
        phone,
        physio,
    )

    # Distraction disabled -> blanks phone
    assert apply_settings({"detectors": {"distraction": False}}, face, phone, physio) == (
        face,
        None,
        physio,
    )

    # Phone disabled -> blanks phone
    assert apply_settings({"detectors": {"phone": False}}, face, phone, physio) == (
        face,
        None,
        physio,
    )

    # Physiology disabled -> blanks physio
    assert apply_settings({"detectors": {"physiology": False}}, face, phone, physio) == (
        face,
        phone,
        None,
    )

    # Multiple disabled
    assert apply_settings(
        {"detectors": {"drowsiness": False, "physiology": False}}, face, phone, physio
    ) == (None, phone, None)


def test_settings_persistence_roundtrip_and_permissions(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    store = SettingsStore(settings_file)

    initial = store.read()
    assert initial["profile"] == "default"
    assert initial["sensitivity"] == "normal"
    assert initial["detectors"]["drowsiness"] is True

    # Update settings
    store.update({"sensitivity": "high", "detectors": {"drowsiness": False}})
    assert settings_file.is_file()

    # Verify 0600 file permissions
    mode = settings_file.stat().st_mode & 0o777
    assert mode == 0o600

    # Reload from new store instance pointing to same file
    store2 = SettingsStore(settings_file)
    reloaded = store2.read()
    assert reloaded["sensitivity"] == "high"
    assert reloaded["detectors"]["drowsiness"] is False
    assert reloaded["detectors"]["distraction"] is True  # preserved default


def test_settings_corrupt_file_falls_back_to_defaults(tmp_path: Path) -> None:
    corrupt_file = tmp_path / "settings.json"
    corrupt_file.write_text("{invalid json content!!!")

    store = SettingsStore(corrupt_file)
    data = store.read()
    assert data["profile"] == "default"
    assert data["sensitivity"] == "normal"
    assert data["detectors"]["drowsiness"] is True


def test_settings_drive_runtime_gate() -> None:
    state = RuntimeState()
    player = PatternPlayer(RecordingBuzzer(), autostart=False)
    now = time.monotonic()
    frame = FrameResult(
        face=FaceReport(state="drowsy", face=True),
        phone=PhoneReport(call=True, phone_score=0.9),
        fps=15.0,
        temp_c=50.0,
        camera_ok=True,
        t=now,
    )
    source = ScriptedFrameSource([frame])
    physio_src = SimpleNamespace(latest=lambda: None)

    active_settings = {"detectors": {"drowsiness": True, "distraction": True}}
    runtime = Runtime(
        source,
        physio_src,  # type: ignore[arg-type]
        player,
        state,
        settings_provider=lambda: active_settings,
    )

    # When drowsiness is enabled -> decision triggers alert
    runtime.on_frame(frame)
    snap = state.snapshot()
    assert snap.decision.pattern != AlertPattern.NONE

    # When drowsiness is disabled -> face is blanked, no drowsiness alert
    active_settings["detectors"]["drowsiness"] = False
    frame2 = FrameResult(
        face=FaceReport(state="drowsy", face=True),
        phone=PhoneReport(call=True, phone_score=0.9),
        fps=15.0,
        temp_c=50.0,
        camera_ok=True,
        t=time.monotonic(),
    )
    runtime.on_frame(frame2)
    snap = state.snapshot()
    # Alert for drowsiness is suppressed because face input was blanked
    assert "drowsy" not in snap.decision.reasons


def test_status_payload_reflects_disabled_detectors() -> None:
    s = Snapshot(
        face=FaceReport(
            state="drowsy",
            perclos=0.4,
            openness=0.2,
            blink_rate=12.0,
            closure_ms=500.0,
            face=True,
        ),
        phone=PhoneReport(call=True, texting=False, phone_p=0.95),
        camera_ok=True,
        fps=15.0,
    )

    # All enabled
    p_all = status_payload(s)
    assert p_all["face"] is True
    assert p_all["state"] == "drowsy"
    assert p_all["call"] is True

    # Drowsiness disabled -> face=False, state="unavailable", perclos omitted
    p_no_face = status_payload(s, {"detectors": {"drowsiness": False}})
    assert p_no_face["face"] is False
    assert p_no_face["state"] == "unavailable"
    assert "perclos" not in p_no_face
    assert p_no_face["call"] is True

    # Phone disabled -> call/texting omitted
    p_no_phone = status_payload(s, {"detectors": {"phone": False}})
    assert "call" not in p_no_phone
    assert p_no_phone["face"] is True
