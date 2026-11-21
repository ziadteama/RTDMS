from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from rtdms_pi.incidents.clip import Mp4Transcoder


class FakeRunner:
    def __init__(self, mode: str = "success") -> None:
        self.mode = mode
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(cmd)
        if self.mode == "missing":
            raise FileNotFoundError("ffmpeg not found")
        if self.mode == "error":
            raise subprocess.CalledProcessError(1, cmd, stderr=b"codec error")

        # In success mode, simulate ffmpeg creating the output tmp file
        out_path = Path(cmd[-1])
        out_path.write_bytes(b"dummy-mp4-data")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")


def test_transcoder_success(tmp_path: Path) -> None:
    inc_dir = tmp_path / "inc1"
    inc_dir.mkdir()
    (inc_dir / "clip.avi").write_bytes(b"dummy-avi")
    meta_path = inc_dir / "meta.json"
    meta_path.write_text(json.dumps({"id": "inc1", "clip_ready": False}))

    runner = FakeRunner(mode="success")
    transcoder = Mp4Transcoder(run=runner)
    assert transcoder.transcode(inc_dir) is True

    # clip.mp4 created and clip_ready updated
    assert (inc_dir / "clip.mp4").is_file()
    assert not (inc_dir / "clip.mp4.tmp").exists()
    meta = json.loads(meta_path.read_text())
    assert meta["clip_ready"] is True
    assert "mp4_error" not in meta


def test_transcoder_error(tmp_path: Path) -> None:
    inc_dir = tmp_path / "inc2"
    inc_dir.mkdir()
    (inc_dir / "clip.avi").write_bytes(b"dummy-avi")
    meta_path = inc_dir / "meta.json"
    meta_path.write_text(json.dumps({"id": "inc2", "clip_ready": False}))

    runner = FakeRunner(mode="error")
    transcoder = Mp4Transcoder(run=runner)
    # Does not raise
    assert transcoder.transcode(inc_dir) is False

    assert not (inc_dir / "clip.mp4").exists()
    meta = json.loads(meta_path.read_text())
    assert meta["clip_ready"] is False
    assert "codec error" in meta.get("mp4_error", "")


def test_transcoder_ffmpeg_missing(tmp_path: Path) -> None:
    inc_dir = tmp_path / "inc3"
    inc_dir.mkdir()
    (inc_dir / "clip.avi").write_bytes(b"dummy-avi")
    meta_path = inc_dir / "meta.json"
    meta_path.write_text(json.dumps({"id": "inc3", "clip_ready": False}))

    runner = FakeRunner(mode="missing")
    transcoder = Mp4Transcoder(run=runner)
    assert transcoder.transcode(inc_dir) is False

    meta = json.loads(meta_path.read_text())
    assert meta["clip_ready"] is False
    assert meta.get("mp4_error") == "ffmpeg missing"


def test_transcoder_queue_and_stop(tmp_path: Path) -> None:
    inc_dir = tmp_path / "inc4"
    inc_dir.mkdir()
    (inc_dir / "clip.avi").write_bytes(b"dummy-avi")
    meta_path = inc_dir / "meta.json"
    meta_path.write_text(json.dumps({"id": "inc4", "clip_ready": False}))

    runner = FakeRunner(mode="success")
    transcoder = Mp4Transcoder(run=runner)
    transcoder.enqueue(inc_dir)
    transcoder.stop(timeout=2.0)

    assert (inc_dir / "clip.mp4").is_file()
