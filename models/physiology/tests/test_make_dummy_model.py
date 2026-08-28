from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dms_physiology.features import FeatureSnapshot
from dms_physiology.model import LogisticModel

TOOL = Path(__file__).resolve().parent.parent / "tools" / "make_dummy_model.py"


def run_tool(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *arguments], capture_output=True, text=True, check=False
    )


def snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        mean_hr_bpm=72.0,
        hr_slope_bpm_per_min=0.5,
        median_ibi_ms=830.0,
        rmssd_ms=42.0,
        sdnn_ms=55.0,
        pnn50=0.2,
        cvnn=0.07,
        valid_interval_count=40,
        artifact_fraction=0.05,
    )


def test_generated_artifact_loads_and_returns_one_half(tmp_path: Path) -> None:
    out = tmp_path / "dummy.json"
    result = run_tool("--out", str(out), "--not-a-trained-model")

    assert result.returncode == 0, result.stderr
    model = LogisticModel.from_json_file(out)
    assert model.version == "dummy-untrained-DO-NOT-DEPLOY"
    assert model.probability(snapshot().model_features()) == 0.5
    assert "no predictive validity" in json.loads(out.read_text(encoding="utf-8"))["warning"]


def test_feature_names_match_runtime_contract(tmp_path: Path) -> None:
    out = tmp_path / "dummy.json"
    assert run_tool("--out", str(out), "--not-a-trained-model").returncode == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["feature_names"] == list(snapshot().model_features())
    assert "log_rmssd" in payload["feature_names"]
    assert "rmssd_ms" not in payload["feature_names"]


def test_refuses_to_write_inside_a_models_directory(tmp_path: Path) -> None:
    out = tmp_path / "models" / "dummy.json"
    result = run_tool("--out", str(out), "--not-a-trained-model")

    assert result.returncode != 0
    assert "models" in result.stderr
    assert not out.exists()


def test_refuses_without_acknowledgement_flag(tmp_path: Path) -> None:
    out = tmp_path / "dummy.json"
    result = run_tool("--out", str(out))

    assert result.returncode != 0
    assert "--not-a-trained-model" in result.stderr
    assert not out.exists()
