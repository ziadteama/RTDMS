from __future__ import annotations

import json
from pathlib import Path

import pytest

from dms_physiology.model import LogisticModel


def valid_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "version": "test-1",
        "feature_names": ["mean_hr_bpm", "log_rmssd"],
        "means": [70.0, 3.0],
        "scales": [10.0, 1.0],
        "coefficients": [0.5, -0.25],
        "intercept": -0.1,
        "threshold": 0.5,
    }


def test_model_loads_and_returns_finite_probability(tmp_path: Path) -> None:
    path = tmp_path / "model.json"
    path.write_text(json.dumps(valid_payload()), encoding="utf-8")
    model = LogisticModel.from_json_file(path)

    assert 0.0 < model.probability({"mean_hr_bpm": 80.0, "log_rmssd": 3.2}) < 1.0


@pytest.mark.parametrize("field,value", [("scales", [0.0, 1.0]), ("feature_names", ["x", "x"])])
def test_model_rejects_invalid_artifact(tmp_path: Path, field: str, value: object) -> None:
    payload = valid_payload()
    payload[field] = value
    path = tmp_path / "model.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        LogisticModel.from_json_file(path)


def test_model_rejects_missing_feature() -> None:
    model = LogisticModel(
        schema_version=1,
        version="test",
        feature_names=("mean_hr_bpm",),
        means=(70.0,),
        scales=(10.0,),
        coefficients=(0.5,),
        intercept=0.0,
        threshold=0.5,
    )

    with pytest.raises(ValueError, match="missing"):
        model.probability({})
