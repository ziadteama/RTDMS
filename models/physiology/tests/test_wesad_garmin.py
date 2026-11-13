"""WESAD/synthetic RR → Garmin RrHrv windows and gated fatigue probability."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from dms_physiology.garmin_hrv import HrvState, RrHrv
from dms_physiology.model import LogisticModel
from dms_physiology.wesad_garmin import (
    WESAD_AMUSEMENT,
    WESAD_BASELINE,
    WESAD_STRESS,
    enrich_hrv_dict,
    fatigue_probability,
    labels_from_quest,
    rr_from_bvp,
    synthetic_subject_rr,
    synthetic_training_rows,
    windows_from_rr,
    write_windows_csv,
)


def test_windows_from_rr_emit_model_feature_columns() -> None:
    rr = synthetic_subject_rr(subject="S", label=0, n_beats=180, seed=1)
    rows = windows_from_rr(rr, label=0, subject_id="S01")
    assert rows
    required = {
        "subject_id",
        "label",
        "mean_hr_bpm",
        "hr_slope_bpm_per_min",
        "median_ibi_ms",
        "log_rmssd",
        "sdnn_ms",
        "pnn50",
        "cvnn",
    }
    assert required <= set(rows[0])
    assert all(row["label"] == 0 for row in rows)
    assert all(row["subject_id"] == "S01" for row in rows)


def test_synthetic_training_rows_have_both_classes_and_subjects() -> None:
    rows = synthetic_training_rows(subjects=4, seed=2)
    assert len(rows) >= 8
    assert {row["label"] for row in rows} == {0, 1}
    assert len({row["subject_id"] for row in rows}) == 4


def test_rr_from_bvp_recovers_plausible_intervals() -> None:
    fs = 64.0
    t = np.arange(0, 30.0, 1.0 / fs)
    # ~72 bpm pulse as a raised cosine train
    period = 60.0 / 72.0
    signal = np.sin(2 * np.pi * t / period)
    signal = np.maximum(signal, 0.0) * 500.0 + 1000.0
    rr = rr_from_bvp(signal, sample_rate_hz=fs)
    assert len(rr) >= 20
    assert 500.0 < float(np.median(rr)) < 1200.0


def test_fatigue_null_when_bad_or_warmup(tmp_path: Path) -> None:
    artifact = {
        "schema_version": 1,
        "version": "unit-test",
        "feature_names": [
            "mean_hr_bpm",
            "hr_slope_bpm_per_min",
            "median_ibi_ms",
            "log_rmssd",
            "sdnn_ms",
            "pnn50",
            "cvnn",
        ],
        "means": [0.0] * 7,
        "scales": [1.0] * 7,
        "coefficients": [0.0] * 7,
        "intercept": 0.0,
        "threshold": 0.5,
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    model = LogisticModel.from_json_file(path)

    hrv = RrHrv()
    snap = hrv.compute(100.0)  # no beats → STALE/WARMUP-ish empty
    assert snap.state in (HrvState.STALE, HrvState.WARMUP, HrvState.BAD)
    prob, version = fatigue_probability(snap, model)
    assert prob is None
    assert version == "unit-test"

    rr = synthetic_subject_rr(subject="S", label=0, n_beats=180, seed=3)
    rows = windows_from_rr(rr, label=0, subject_id="S")
    assert rows
    # Rebuild a VALID snapshot via windows path: enrich on a fresh stream.
    from dms_physiology.wesad_garmin import feed_rr

    live = RrHrv()
    t = feed_rr(live, rr)
    valid = live.compute(t)
    assert valid.state in (HrvState.VALID, HrvState.DEGRADED)
    prob2, _ = fatigue_probability(valid, model)
    assert prob2 == pytest.approx(0.5)
    enriched = enrich_hrv_dict(valid, model)
    assert enriched["fatigue_probability"] == pytest.approx(0.5)
    assert enriched["model_version"] == "unit-test"


def test_write_windows_csv_round_trip(tmp_path: Path) -> None:
    rows = synthetic_training_rows(subjects=2, seed=4)
    out = tmp_path / "w.csv"
    n = write_windows_csv(out, rows)
    assert n == len(rows)
    text = out.read_text(encoding="utf-8")
    assert "log_rmssd" in text.splitlines()[0]


def test_labels_from_quest_marks_base_and_tsst(tmp_path: Path) -> None:
    quest = tmp_path / "S2_quest.csv"
    quest.write_text(
        "\n".join(
            [
                "# ORDER;Base;TSST;Fun;;;;",
                "# START;1.0;3.0;5.0;;;;",
                "# END;2.0;4.0;6.0;;;;",
            ]
        ),
        encoding="utf-8",
    )
    hz = 64.0
    labels = labels_from_quest(quest, bvp_len=int(7 * 60 * hz), sample_rate_hz=hz)
    assert int(labels[int(1.5 * 60 * hz)]) == WESAD_BASELINE
    assert int(labels[int(3.5 * 60 * hz)]) == WESAD_STRESS
    assert int(labels[int(5.5 * 60 * hz)]) == WESAD_AMUSEMENT
    assert int(labels[0]) == 0


def test_segment_ibi_by_quest_uses_time_column(tmp_path: Path) -> None:
    from dms_physiology.wesad_garmin import segment_ibi_by_quest

    quest = tmp_path / "S2_quest.csv"
    quest.write_text(
        "\n".join(
            [
                "# ORDER;Base;TSST;;;;",
                "# START;0.1;0.3;;;;",
                "# END;0.2;0.4;;;;",
            ]
        ),
        encoding="utf-8",
    )
    # times in seconds; RR in ms
    ibi = [(8.0, 800.0), (9.0, 810.0), (20.0, 700.0), (22.0, 690.0)]
    parts = segment_ibi_by_quest(ibi, quest)
    by_lab = {lab: rr for lab, rr in parts}
    assert by_lab[WESAD_BASELINE] == [800.0, 810.0]
    assert by_lab[WESAD_STRESS] == [700.0, 690.0]
