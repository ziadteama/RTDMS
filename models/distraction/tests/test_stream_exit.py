"""stream.py must exit non-zero when the camera cannot be opened (systemd then backs off)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stream  # noqa: E402


def _run(monkeypatch, exc: Exception) -> int:
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(stream, "open_source", boom)
    return stream.main(["--host", "127.0.0.1", "--port", "0", "--no-detect"])


def test_no_camera_exits_nonzero(monkeypatch):
    assert _run(monkeypatch, RuntimeError("No camera number 0 found")) == 1


def test_no_frames_exits_nonzero(monkeypatch):
    assert _run(monkeypatch, RuntimeError("camera produced no frames within 5 s")) == 1
