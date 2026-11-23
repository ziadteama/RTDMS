"""The calibration run publishes its step so the phone can follow it instead of its own timers."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
_face_src = Path(__file__).resolve().parents[2] / "face" / "src"
if _face_src.is_dir() and str(_face_src) not in sys.path:
    sys.path.insert(0, str(_face_src))

pytest.importorskip("dms_face", reason="models/face not on path")

import drowsiness  # noqa: E402
from dms_face.config import Config  # noqa: E402


def frame(face: bool = True) -> SimpleNamespace:
    return SimpleNamespace(face_present=face, ear_raw=0.3 if face else None, gaze_h=0.0,
                           gaze_v=0.0, angles=(0.0, 0.0, 0.0))


def test_steps_follow_the_unit_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(drowsiness.time, "monotonic", lambda: now[0])
    cal = drowsiness.Calibration(Config(), "test")
    seen = []

    def at(t: float, face: bool = True) -> None:
        now[0] = 100.0 + t
        cal.update(frame(face))
        if not seen or seen[-1] != cal.step:
            seen.append(cal.step)

    at(0, face=False)
    assert cal.step == "waiting_face" and cal.left_s is None
    at(1)
    assert cal.step == "countdown_open" and cal.left_s == pytest.approx(2.0)  # restarted at t=0
    t = 1.0
    while cal.index == 0 and t < 40:
        t += 0.1
        at(t)
    for _ in range(40):
        t += 0.1
        at(t)
    assert seen[:4] == ["waiting_face", "countdown_open", "open", "countdown_closed"]
    assert "closed" in seen
    assert cal.left_s is not None and cal.left_s >= 0
