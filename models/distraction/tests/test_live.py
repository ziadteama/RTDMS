"""Live-mode pieces that run without a camera: profiles, colour path, scorer, overlay."""

import sys
from pathlib import Path

import numpy as np
from helpers import det, make_face

from rtdms_distraction.config import PipelineConfig, RulesConfig, load_pipeline_config
from rtdms_distraction.pipeline import DistractionPipeline
from rtdms_distraction.viz import render

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import live  # noqa: E402


def test_profile_merges_over_base():
    base = load_pipeline_config()
    prof = load_pipeline_config(profile="laptop_webcam")
    assert (prof.capture.width, prof.capture.height) == (1280, 720)
    assert prof.rectify.enabled is False and prof.roi.rect is None
    assert prof.capture.grayscale is True and prof.live.side_check is True
    assert [m.hands for m in prof.live.models][:3] == ["mediapipe", "detector", "detector"]
    # untouched keys come from pipeline.yaml
    assert prof.facemesh.crop_size == base.facemesh.crop_size
    assert base.capture.width == 1296


class Fake:
    def __init__(self, dets):
        self.dets = dets

    def detect(self, view):
        assert view.ndim == 3
        return self.dets

    def process(self, view, t):
        assert view.ndim == 3
        return make_face()


def build(dets=()):
    p = PipelineConfig()
    p.rectify.enabled = False
    p.hands.source = "detector"
    r = RulesConfig()
    r.baseline.duration_s = 0.0
    r.baseline.min_samples = 1
    f = Fake(list(dets))
    return DistractionPipeline(p, r, (640, 640), detector=f, facemesh=f)


def test_pipeline_accepts_colour_and_gray_frames():
    pipe = build()
    a = pipe.process(np.zeros((640, 640), np.uint8), 0.0)
    b = pipe.process(np.zeros((640, 640, 3), np.uint8), 0.1)
    assert a.view.ndim == 2 and b.view.ndim == 3
    img = render(b, 10.0, debug=False, info=["model x"], banner="Phone call at your RIGHT ear")
    assert img.ndim == 3 and img.shape[0] >= 560


def test_guided_scorer_hits_false_alarms_and_tta():
    script = [(0, 2, "normal", "n"), (2, 5, "drinking", "d"), (5, 7, "neg_talking", "t")]
    sc = live.GuidedScorer(script)
    cup = [det("drink", 320, 300, 50, 70)]
    pipe_cup, pipe_none = build(cup), build()
    t = 0.0
    while t < 7.0:
        res = (pipe_cup if 2.0 <= t < 5.0 else pipe_none).process(np.zeros((640, 640), np.uint8), t)
        sc.update(t, res, "m1")
        t += 1 / 30
    rows = {r["segment"]: r for r in sc.summary()}
    d = rows["drinking"]
    assert d["hit_rate"] > 0.4 and d["raw_rate"] > 0.95
    assert d["alerts_raised"] == 1 and d["false_alarms"] == 0
    assert 0.9 < d["time_to_alert_s"] < 1.5
    assert rows["neg_talking"]["hit_rate"] is None


def test_discover_models_skips_missing_and_finds_extra(tmp_path, monkeypatch):
    extra = tmp_path / "models" / "v9_416_ncnn_model"
    extra.mkdir(parents=True)
    (extra / "metadata.yaml").write_text("imgsz: [416, 416]\nnames: {0: phone, 1: hand}\n")
    monkeypatch.setattr(live, "ROOT", tmp_path)
    got = live.discover_models([live.LiveModel("gone", str(tmp_path / "nope"))])
    assert [(m.name, m.hands, m.imgsz) for m in got] == [("v9_416", "detector", 416)]


def test_reports_written_as_json_and_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    rows = [{"segment": "drinking", "start_s": 0, "end_s": 10, "frames": 100, "hit_rate": 0.5,
             "raw_rate": 0.8, "alerts_raised": 1, "false_alarms": 0,
             "false_alarm_behaviours": [], "time_to_alert_s": 1.2, "models": ["m"]},
            {"segment": "normal", "start_s": 10, "end_s": 15, "frames": 50, "hit_rate": None,
             "raw_rate": None, "alerts_raised": 1, "false_alarms": 1,
             "false_alarm_behaviours": ["eating"], "time_to_alert_s": None, "models": ["m"]}]
    meta = {"utc": "X", "models_used": ["m"], "conf_final": 0.25, "grayscale_final": True,
            "flip": False, "fps_cap": None, "measured_fps": 20.0}
    stem = live.write_reports(rows, meta)
    md = stem.with_suffix(".md").read_text()
    assert "| drinking | 50% | 80% | 1 | 0 | 1.2 |" in md
    assert "False alarms during the 'normal' gaps: 1" in md
    assert stem.with_suffix(".json").is_file()
