"""The shadow artifact stays compatible with dependency-free deployment inference."""

from pathlib import Path

from dms_physiology.model import LogisticModel

ARTIFACT = Path(__file__).resolve().parents[1] / "models" / "hr_shadow_mpddf_v1.json"


def test_hr_shadow_artifact() -> None:
    model = LogisticModel.from_json_file(ARTIFACT)
    assert model.version == "hr_shadow_mpddf_v1"
    assert model.feature_names == ("hr_delta_bpm", "hr_trend_bpm_per_10min")
    typical = {"hr_delta_bpm": -5.0, "hr_trend_bpm_per_10min": -1.0}
    assert 0 <= model.probability(typical) <= 1
    for name, coefficient in zip(model.feature_names, model.coefficients, strict=True):
        lower = model.probability({**typical, name: typical[name] - 1.0})
        upper = model.probability({**typical, name: typical[name] + 1.0})
        assert 0 <= lower <= 1
        assert 0 <= upper <= 1
        if coefficient > 0:
            assert upper > lower
        elif coefficient < 0:
            assert upper < lower
        else:
            assert upper == lower
