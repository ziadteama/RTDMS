"""Distraction classifier backends.

Pi path: ONNX Runtime on exported YOLOv8n-cls (Safe-Drive-TN / State Farm).
Softmax over c0..c9 is collapsed to {safe, phone, eating} for fusion.
Stub backend keeps CI green with no weights.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import DetectorConfig
from .paths import resolve_under_package
from .types import DistractionClass, QualityReason, QualityReport, QualityState


@dataclass(frozen=True, slots=True)
class DetectResult:
    probs: dict[DistractionClass, float]
    quality: QualityReport
    backend: str


def collapse_probs(
    raw: dict[str, float],
    collapse_map: dict[str, str],
) -> dict[DistractionClass, float]:
    """Sum State Farm (or similar) class probs into safe / phone / eating."""
    out = {
        DistractionClass.SAFE: 0.0,
        DistractionClass.PHONE: 0.0,
        DistractionClass.EATING: 0.0,
    }
    for name, p in raw.items():
        dest = collapse_map.get(name, "safe")
        out[DistractionClass(dest)] += float(p)
    total = sum(out.values())
    if total > 0:
        for k in out:
            out[k] /= total
    return out


class StubDetector:
    """Deterministic stub — always safe with good quality. No model file required."""

    def __init__(self, cfg: DetectorConfig) -> None:
        self.cfg = cfg

    def predict(self, frame_bgr: np.ndarray | None) -> DetectResult:
        if frame_bgr is None or frame_bgr.size == 0:
            return DetectResult(
                probs={
                    DistractionClass.SAFE: 0.0,
                    DistractionClass.PHONE: 0.0,
                    DistractionClass.EATING: 0.0,
                },
                quality=QualityReport(QualityState.BAD, 0.0, QualityReason.BAD_INPUT),
                backend="stub",
            )
        return DetectResult(
            probs={
                DistractionClass.SAFE: 0.90,
                DistractionClass.PHONE: 0.05,
                DistractionClass.EATING: 0.05,
            },
            quality=QualityReport(QualityState.GOOD, 1.0, QualityReason.NONE),
            backend="stub",
        )


class OnnxDetector:
    """Lazy ONNX Runtime classifier. Instantiates only when a model file exists."""

    def __init__(self, cfg: DetectorConfig) -> None:
        self.cfg = cfg
        self._session = None
        self._input_name: str | None = None
        self._model_path = str(resolve_under_package(cfg.model_path))

    def _ensure_session(self) -> None:
        if self._session is not None:
            return
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            self._model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name

    def predict(self, frame_bgr: np.ndarray | None) -> DetectResult:
        if frame_bgr is None or frame_bgr.size == 0:
            return DetectResult(
                probs={c: 0.0 for c in DistractionClass},
                quality=QualityReport(QualityState.BAD, 0.0, QualityReason.BAD_INPUT),
                backend="onnx",
            )
        try:
            self._ensure_session()
        except Exception:
            return DetectResult(
                probs={c: 0.0 for c in DistractionClass},
                quality=QualityReport(QualityState.BAD, 0.0, QualityReason.NO_MODEL),
                backend="onnx",
            )

        assert self._session is not None and self._input_name is not None
        try:
            import cv2

            size = self.cfg.input_size
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            resized = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_LINEAR)
            x = resized.astype(np.float32) / 255.0
            x = np.transpose(x, (2, 0, 1))[None, ...]
            out = self._session.run(None, {self._input_name: x})[0]
            logits = np.asarray(out, dtype=np.float32).reshape(-1)
            e = np.exp(logits - np.max(logits))
            probs_arr = e / np.sum(e)
            names = self.cfg.class_names
            if len(probs_arr) != len(names):
                return DetectResult(
                    probs={c: 0.0 for c in DistractionClass},
                    quality=QualityReport(QualityState.BAD, 0.0, QualityReason.INFERENCE_ERROR),
                    backend="onnx",
                )
            raw = {names[i]: float(probs_arr[i]) for i in range(len(names))}
            probs = collapse_probs(raw, self.cfg.collapse_map)
            top = max(probs.values())
            if top < self.cfg.min_confidence:
                q = QualityReport(QualityState.DEGRADED, float(top), QualityReason.LOW_CONFIDENCE)
            else:
                q = QualityReport(QualityState.GOOD, float(top), QualityReason.NONE)
            return DetectResult(probs=probs, quality=q, backend="onnx")
        except Exception:
            return DetectResult(
                probs={c: 0.0 for c in DistractionClass},
                quality=QualityReport(QualityState.BAD, 0.0, QualityReason.INFERENCE_ERROR),
                backend="onnx",
            )


def make_detector(cfg: DetectorConfig, *, prefer_onnx: bool = True) -> StubDetector | OnnxDetector:
    path = resolve_under_package(cfg.model_path)
    if prefer_onnx and path.is_file():
        return OnnxDetector(cfg)
    return StubDetector(cfg)
