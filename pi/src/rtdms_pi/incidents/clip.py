"""Background transcode worker for incident clips."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any


class Mp4Transcoder:
    def __init__(
        self,
        run: Callable[..., Any] | None = None,
        ffmpeg_bin: str = "ffmpeg",
    ) -> None:
        self.run = run or subprocess.run
        self.ffmpeg_bin = ffmpeg_bin
        self._queue: queue.Queue[Path | None] = queue.Queue()
        self._worker_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._running = False

    def _update_meta(self, meta_path: Path, **kwargs: Any) -> None:
        if not meta_path.is_file():
            return
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta.update(kwargs)
            tmp_meta = meta_path.with_suffix(".tmp")
            tmp_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            tmp_meta.replace(meta_path)
        except OSError:
            pass

    def _run_ffmpeg(self, avi_path: Path, tmp_mp4: Path) -> Any:
        cmd = [
            "nice",
            "-n",
            "19",
            self.ffmpeg_bin,
            "-y",
            "-i",
            str(avi_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-movflags",
            "+faststart",
            str(tmp_mp4),
        ]
        return self.run(cmd, check=True, capture_output=True)

    def transcode(self, incident_dir: Path) -> bool:
        avi_path = incident_dir / "clip.avi"
        if not avi_path.is_file():
            return False
        meta_path = incident_dir / "meta.json"
        tmp_mp4 = incident_dir / "clip.mp4.tmp"
        target_mp4 = incident_dir / "clip.mp4"

        try:
            proc = self._run_ffmpeg(avi_path, tmp_mp4)
            if hasattr(proc, "returncode") and proc.returncode != 0:
                self._update_meta(meta_path, mp4_error=f"ffmpeg exit {proc.returncode}")
                return False
            if tmp_mp4.is_file():
                tmp_mp4.replace(target_mp4)
                self._update_meta(meta_path, clip_ready=True)
                return True
            self._update_meta(meta_path, mp4_error="output file missing")
            return False
        except FileNotFoundError:
            self._update_meta(meta_path, mp4_error="ffmpeg missing")
            return False
        except Exception as err:
            stderr = getattr(err, "stderr", None)
            if isinstance(stderr, bytes):
                msg = stderr.decode("utf-8", errors="replace")
            else:
                msg = str(err)
            self._update_meta(meta_path, mp4_error=msg[:120])
            return False
        finally:
            if tmp_mp4.is_file():
                try:
                    tmp_mp4.unlink()
                except OSError:
                    pass

    def _worker(self) -> None:
        while self._running:
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                self._queue.task_done()
                break
            try:
                self.transcode(item)
            finally:
                self._queue.task_done()

    def start(self) -> None:
        with self._lock:
            if self._running and self._worker_thread and self._worker_thread.is_alive():
                return
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._worker, daemon=True, name="mp4-transcode"
            )
            self._worker_thread.start()

    def enqueue(self, incident_dir: Path) -> None:
        self.start()
        self._queue.put(incident_dir)

    def stop(self, timeout: float = 3.0) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._queue.put(None)
            thread = self._worker_thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
