"""Unit tests for phone distraction package."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from dms_phone.config import STATEFARM_COLLAPSE, Config
from dms_phone.detector import OnnxDetector, StubDetector, collapse_probs, make_detector
from dms_phone.fusion import InMemorySink
from dms_phone.pipeline import PhonePipeline
from dms_phone.types import DistractionClass, OutputState, QualityState

ONNX = Path(__file__).resolve().parents[1] / "models" / "phone_cls.onnx"


def test_stub_predicts_safe():
    det = StubDetector(Config().detector)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    r = det.predict(frame)
    assert r.quality.state is QualityState.GOOD
    assert r.probs[DistractionClass.SAFE] > 0.5


def test_bad_input_nulls_scores():
    pipe = PhonePipeline(detector=StubDetector(Config().detector))
    out = pipe.process(None, now=1.0)
    assert out is not None
    assert out.state is OutputState.UNAVAILABLE
    assert out.phone_score is None
    assert out.eating_score is None


def test_rate_limit_skips_ticks():
    pipe = PhonePipeline(detector=StubDetector(Config().detector))
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    first = pipe.process(frame, now=10.0)
    second = pipe.process(frame, now=10.05)
    assert first is not None
    assert second is None


def test_output_dict_schema():
    pipe = PhonePipeline(detector=StubDetector(Config().detector))
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    out = pipe.process(frame, now=1.0)
    assert out is not None
    d = out.to_dict()
    assert d["schema_version"] == 1
    assert d["top_class"] == "safe"
    assert "phone_score" in d


def test_inmemory_sink():
    sink = InMemorySink()

    async def _run() -> None:
        await sink.publish({"ok": True})

    asyncio.run(_run())
    assert sink.outputs == [{"ok": True}]


def test_collapse_phone_and_eating():
    raw = {f"c{i}": 0.0 for i in range(10)}
    raw["c2"] = 0.4
    raw["c4"] = 0.3
    raw["c6"] = 0.2
    raw["c0"] = 0.1
    collapsed = collapse_probs(raw, STATEFARM_COLLAPSE)
    assert collapsed[DistractionClass.PHONE] == pytest.approx(0.7)
    assert collapsed[DistractionClass.EATING] == pytest.approx(0.2)
    assert collapsed[DistractionClass.SAFE] == pytest.approx(0.1)


@pytest.mark.skipif(not ONNX.is_file(), reason="phone_cls.onnx missing")
def test_onnx_runs_and_collapses():
    cfg = Config()
    det = OnnxDetector(cfg.detector)
    frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
    r = det.predict(frame)
    assert r.backend == "onnx"
    assert set(r.probs) == set(DistractionClass)
    assert abs(sum(r.probs.values()) - 1.0) < 1e-3
    assert r.quality.state in (QualityState.GOOD, QualityState.DEGRADED, QualityState.BAD)


@pytest.mark.skipif(not ONNX.is_file(), reason="phone_cls.onnx missing")
def test_make_detector_prefers_onnx():
    det = make_detector(Config().detector)
    assert isinstance(det, OnnxDetector)
