import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from dms_face.calibration import BaselineAdapter, DriverProfile, profile_from_phone

PAYLOAD = {
    "source": "phone", "closed_ratio": 0.38, "ear_open": 0.29, "ear_closed": 0.11,
    "snr": 46.2, "quality": "good", "samples_open": 118, "samples_closed": 21,
    "created": 1795189202400,
}


@pytest.mark.parametrize("quality", ["good", "fair"])
@pytest.mark.parametrize("ratio", [0.1, 0.38, 0.8])
def test_accept(quality, ratio):
    current = DriverProfile(ear_open=0.4, gaze_h0=0.6, yaw0=12, created=1)
    before = asdict(current)
    result = profile_from_phone(dict(PAYLOAD, quality=quality, closed_ratio=ratio), current)
    expected = dict(before, ear_closed=ratio * 0.4, closed_ratio=ratio,
                    notes="phone", created=result.created)
    assert asdict(result) == expected
    assert result.created > 1
    assert asdict(current) == before


@pytest.mark.parametrize("key,value,reason", [
    ("source", "pi", "source"),
    ("closed_ratio", None, "closed_ratio"),
    ("closed_ratio", "0.38", "closed_ratio"),
    ("closed_ratio", True, "closed_ratio"),
    ("closed_ratio", float("nan"), "closed_ratio"),
    ("closed_ratio", float("inf"), "closed_ratio"),
    ("closed_ratio", 0.09, "outside"),
    ("closed_ratio", 0.81, "outside"),
    ("quality", "poor", "poor"),
    ("quality", "unknown", "quality"),
    ("quality", [], "quality"),
    ("ear_open", None, "ear_open"),
    ("ear_closed", "0.11", "ear_closed"),
    ("ear_open", True, "ear_open"),
    ("ear_closed", float("nan"), "ear_closed"),
    ("ear_open", 0, "range"),
    ("ear_closed", -0.1, "range"),
    ("ear_open", 1.1, "range"),
    ("ear_closed", 1.1, "range"),
    ("ear_closed", 0.26, "too close"),
    ("snr", -1, "snr"),
    ("samples_open", 0, "positive"),
    ("samples_closed", 1.5, "integer"),
    ("created", False, "created"),
    ("extra", 1, "unknown"),
])
def test_reject(key, value, reason):
    current = DriverProfile()
    before = asdict(current)
    with pytest.raises(ValueError, match=reason):
        profile_from_phone(dict(PAYLOAD, **{key: value}), current)
    assert asdict(current) == before


@pytest.mark.parametrize("key", list(PAYLOAD))
def test_missing(key):
    payload = dict(PAYLOAD)
    del payload[key]
    with pytest.raises(ValueError, match=key):
        profile_from_phone(payload, DriverProfile())


@pytest.mark.parametrize("payload", [None, [], "phone", 1, True])
def test_non_object(payload):
    with pytest.raises(ValueError, match="object"):
        profile_from_phone(payload, DriverProfile())


def test_save_load(tmp_path):
    profile = profile_from_phone(PAYLOAD, DriverProfile())
    path = profile.save(tmp_path)
    assert DriverProfile.load("default", tmp_path) == profile
    data = json.loads(open(path).read())
    assert data.pop("closed_ratio") == 0.38
    data["future_field"] = "ignored"
    with open(path, "w") as f:
        json.dump(data, f)
    loaded = DriverProfile.load("default", tmp_path)
    assert loaded.closed_ratio is None
    assert loaded.ear_closed == profile.ear_closed


@pytest.mark.parametrize("ratio", [None, 0.38])
@pytest.mark.parametrize("candidate", [0.4, -10])
def test_adaptation_and_floor(ratio, candidate):
    profile = DriverProfile(closed_ratio=ratio)
    cfg = SimpleNamespace(adapt_window_s=60, adapt_enabled=True, adapt_hz=1,
                          adapt_percentile=90)
    adapter = BaselineAdapter(cfg, profile)
    for i in range(120):
        adapter.push(candidate, i / 10)
    old_closed = profile.ear_closed
    expected = max(old_closed + 0.05, 0.9 * profile.ear_open + 0.1 * candidate)
    assert adapter.maybe_adapt(12, False) == pytest.approx(expected)
    assert profile.ear_closed == pytest.approx(old_closed if ratio is None else ratio * expected)
    assert adapter.maybe_adapt(14, True) == pytest.approx(expected)
