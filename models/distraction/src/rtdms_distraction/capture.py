"""Frame sources. Every source yields single-channel uint8 grayscale plus a timestamp.

Grayscale everywhere makes daytime NoIR (pinkish colour) and night IR (monochrome) look like the
same domain to the detector. It is expanded back to 3 channels only after the ROI step, on the
small driver view, because MediaPipe and YOLO both want 3-channel input.

    picamera2 (Pi)      YUV420 at the full-FOV binned mode; the Y plane IS the grayscale image
    OpenCV webcam (PC)  BGR -> gray
    video file          BGR -> gray, timestamps from the file's frame rate (repeatable runs)
"""

from __future__ import annotations

import json
import platform
import threading
import time
from pathlib import Path

import cv2
import numpy as np


def to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame
    if frame.shape[2] == 1:
        return frame[:, :, 0]
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def is_raspberry_pi() -> bool:
    try:
        with open("/proc/device-tree/model", "rb") as f:
            return b"Raspberry Pi" in f.read()
    except OSError:
        return False


class FrameSource:
    """read() -> (gray, timestamp_s) or (None, None) at end of stream."""

    size: tuple[int, int]

    def start(self) -> FrameSource:
        return self

    def read(self) -> tuple[np.ndarray | None, float | None]:
        raise NotImplementedError

    def stop(self) -> None:
        pass

    def describe(self) -> str:
        return type(self).__name__

    def __enter__(self) -> FrameSource:
        return self.start()

    def __exit__(self, *exc) -> bool:
        self.stop()
        return False


class _Threaded(FrameSource):
    """Live sources grab on a background thread so the pipeline always gets the newest frame
    and a slow inference never backs up the camera queue. read() blocks until a frame newer
    than the last one returned is available."""

    def __init__(self) -> None:
        self._frame: np.ndarray | None = None
        self._ts: float | None = None
        self._seq = 0
        self._read_seq = 0
        self._cond = threading.Condition()
        self._running = False
        self._thread: threading.Thread | None = None
        self.grab_ms = 0.0  # time spent in the most recent camera read

    def _grab(self) -> np.ndarray | None:
        raise NotImplementedError

    def _loop(self) -> None:
        while self._running:
            t0 = time.perf_counter()
            frame = self._grab()
            dt = (time.perf_counter() - t0) * 1000
            if frame is None:
                time.sleep(0.002)
                continue
            with self._cond:
                self._frame, self._ts = frame, time.monotonic()
                self._seq += 1
                self.grab_ms = dt
                self._cond.notify_all()

    def start(self) -> FrameSource:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="capture")
        self._thread.start()
        with self._cond:
            if not self._cond.wait_for(lambda: self._frame is not None, timeout=5.0):
                raise RuntimeError("camera produced no frames within 5 s")
        return self

    def read(self) -> tuple[np.ndarray | None, float | None]:
        with self._cond:
            self._cond.wait_for(lambda: self._seq > self._read_seq or not self._running, 1.0)
            self._read_seq = self._seq
            return self._frame, self._ts

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)


class PiCameraSource(_Threaded):
    def __init__(self, width: int, height: int, fps: int, flip: bool = False):
        super().__init__()
        from picamera2 import Picamera2  # Pi only

        self.size = (width, height)
        self._flip = flip
        self._cam = Picamera2()
        config = self._cam.create_video_configuration(
            main={"size": (width, height), "format": "YUV420"},
            # Pin the sensor mode: without this libcamera may pick a cropped mode whose output
            # happens to be larger, silently narrowing the field of view.
            sensor={"output_size": (width, height)},
            controls={"FrameRate": fps},
            buffer_count=4,
        )
        self._cam.configure(config)
        self._cam.start()
        time.sleep(0.5)  # AE settle

    def _grab(self) -> np.ndarray | None:
        yuv = self._cam.capture_array("main")
        w, h = self.size
        y = yuv[:h, :w]  # rows past h are the chroma planes; columns past w are stride padding
        return cv2.flip(y, 1) if self._flip else y

    def stop(self) -> None:
        super().stop()
        self._cam.stop()
        self._cam.close()

    def describe(self) -> str:
        return f"picamera2 YUV420/Y {self.size[0]}x{self.size[1]}"


class WebcamSource(_Threaded):
    def __init__(self, index: int, width: int, height: int, fps: int, flip: bool = False):
        super().__init__()
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(index, backend)
        if not self._cap.isOpened():
            raise RuntimeError(f"could not open camera index {index}")
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._flip = flip
        self._index = index
        self.size = (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                     int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    def _grab(self) -> np.ndarray | None:
        ok, bgr = self._cap.read()
        if not ok:
            return None
        gray = to_gray(bgr)
        return cv2.flip(gray, 1) if self._flip else gray

    def stop(self) -> None:
        super().stop()
        self._cap.release()

    def describe(self) -> str:
        return f"webcam #{self._index} {self.size[0]}x{self.size[1]}"


class VideoFileSource(FrameSource):
    """Sequential decode, no frame dropping. Timestamps come from the file's frame rate, so every
    time-based rule sees video time regardless of how fast this machine processes."""

    def __init__(self, path: str | Path, realtime: bool = False):
        self.path = str(path)
        self._cap = cv2.VideoCapture(self.path)
        if not self._cap.isOpened():
            raise RuntimeError(f"could not open video: {path}")
        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        # record.py writes the REAL capture rate to a sidecar .json: webcams often deliver less
        # than the container header claims, and every time-based rule needs the true clock.
        meta = Path(path).with_suffix(".json")
        if meta.is_file():
            measured = json.loads(meta.read_text(encoding="utf8")).get("measured_fps")
            if measured:
                self.fps = float(measured)
        self.frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.size = (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                     int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self.realtime = realtime
        self._i = 0
        self._t0 = 0.0
        self.grab_ms = 0.0

    def start(self) -> FrameSource:
        self._t0 = time.monotonic()
        return self

    def read(self) -> tuple[np.ndarray | None, float | None]:
        t0 = time.perf_counter()
        ok, bgr = self._cap.read()
        if not ok:
            return None, None
        gray = to_gray(bgr)
        self.grab_ms = (time.perf_counter() - t0) * 1000
        ts = self._i / self.fps
        self._i += 1
        if self.realtime:
            delay = self._t0 + ts - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        return gray, ts

    def stop(self) -> None:
        self._cap.release()

    def describe(self) -> str:
        return f"video {self.path} ({self.frame_count} frames @ {self.fps:.1f} fps)"


def open_source(
    width: int, height: int, fps: int, video: str | None = None, camera_index: int | None = None,
    flip: bool = False, realtime: bool = False,
) -> FrameSource:
    """Video file if given; else picamera2 on a Pi; else an OpenCV webcam."""
    if video is not None:
        return VideoFileSource(video, realtime=realtime)
    if camera_index is None and is_raspberry_pi():
        return PiCameraSource(width, height, fps, flip)
    return WebcamSource(camera_index or 0, width, height, fps, flip)
