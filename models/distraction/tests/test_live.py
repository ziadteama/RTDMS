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
    assert prof.capture.grayscale is False and prof.live.side_check is True  # colour target
    assert [m.name for m in prof.live.models][:2] == ["det_v2b", "stock yolo26n"]
    assert prof.detector.weights == prof.live.models[0].weights  # the default detector first
    assert [m.hands for m in prof.live.models][1:4] == ["mediapipe", "detector", "detector"]
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
    p.pose.enabled = False  # unit tests never load model files
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


def test_scorer_compares_setups_and_scratching_stays_below_dwell():
    script = [(0, 2, "normal", "n"), (2, 8, "phone_right_ear", "r"), (8, 13, "neg_scratch", "s")]
    sc = live.GuidedScorer(script)
    hand = [det("hand", 215, 270, 50, 50)]  # centred in the right ear zone
    with_hand = build(hand)
    t = 0.0
    while t < 13.0:
        at_ear = 2.0 <= t < 8.0 or 8.5 <= t < 9.5 or 10.5 <= t < 11.5  # 1 s scratches
        # one pipeline throughout (the rule engine keeps the episode); swap its detections
        with_hand.detector.dets = hand if at_ear else []
        res = with_hand.process(np.zeros((640, 640), np.uint8), t)
        sc.update(t, res, "m")
        t += 1 / 30
    rows = {r["segment"]: r for r in sc.summary()}
    r = rows["phone_right_ear"]["setups"]["hands"]
    assert r["ear_hit_rate"] > 0.4 and 2.9 < r["ear_time_to_alert_s"] < 3.2
    assert rows["neg_scratch"]["setups"]["hands"]["ear_false_alarms"] == 0


class FakeEarClf:
    def __init__(self, p):
        self.p = p

    def update(self, view, face, fw):
        return {"phone_right_ear": self.p, "phone_left_ear": 0.0}


def test_guided_compares_two_ear_models_on_the_same_frames(tmp_path, monkeypatch):
    script = [(0, 2, "normal", "n"), (2, 8, "phone_right_ear", "r"), (8, 13, "neg_scratch", "s")]
    hand = [det("hand", 215, 270, 50, 50)]  # centred in the right ear zone
    pipe = build(hand)
    pipe.ear_clf, pipe.pose_on, pipe.clf_on = FakeEarClf(0.9), True, True  # sees the phone
    pipe.ear_alts["m128"] = FakeEarClf(0.1)  # misses it
    alt = pipe.rules.add_clf_variant("m128")
    sc = live.GuidedScorer(script, pipe.rules.variants, [("m160", None), ("m128", "m128")])
    t = 0.0
    while t < 13.0:
        pipe.detector.dets = hand if 2.0 <= t < 8.0 else []
        sc.update(t, pipe.process(np.zeros((640, 640), np.uint8), t), "m")
        t += 1 / 30
    rows = sc.summary()
    by = {r["segment"]: r for r in rows}
    ear = by["phone_right_ear"]
    a, b = ear["setups"]["hands+pose+clf"], ear["setups"][alt]
    assert a["ear_hit_rate"] == b["ear_hit_rate"] > 0.4  # same hand dwell -> same WARNINGs
    assert a["ear_alert_rate"] > 0.4 and b["ear_alert_rate"] == 0.0
    assert ear["ear_models"]["m160"]["phone_rate"] == 1.0
    assert ear["ear_models"]["m128"]["phone_rate"] == 0.0
    monkeypatch.setattr(live, "ROOT", tmp_path)
    meta = {"utc": "X", "models_used": ["m"], "conf_final": 0.25, "grayscale_final": False,
            "flip": False, "fps_cap": None, "measured_fps": 20.0, "classifier_loaded": True,
            "ear_model": "m160"}
    md = live.write_reports(rows, meta).with_suffix(".md").read_text()
    assert "hands+pose+clf [m160]" in md and "hands+pose+clf [m128]" in md
    assert "| m160 | 100% |" in md and "Suggested ear model: m160" in md
