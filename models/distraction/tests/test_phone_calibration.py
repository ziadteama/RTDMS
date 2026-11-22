"""Phone calibration without a camera or neural runtime."""

import json
import sys
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
_face_src = Path(__file__).resolve().parents[2] / "face" / "src"
if _face_src.is_dir() and str(_face_src) not in sys.path:
    sys.path.insert(0, str(_face_src))

pytest.importorskip("dms_face", reason="models/face not on path")

from drowsiness import Drowsiness, parse_phone_calibration  # noqa: E402, I001
from dms_face.calibration import DriverProfile  # noqa: E402

PAYLOAD = {
    "source": "phone", "closed_ratio": 0.38, "ear_open": 0.29, "ear_closed": 0.11,
    "snr": 46.2, "quality": "good", "samples_open": 118, "samples_closed": 21,
    "created": 1795189202400,
}


def test_parse_accept():
    assert parse_phone_calibration(json.dumps(PAYLOAD).encode()) == PAYLOAD


@pytest.mark.parametrize("body,reason", [
    (b"{", "invalid JSON"), (b"\xff", "invalid JSON"), (b"[]", "object"),
    (b"null", "object"), (json.dumps(dict(PAYLOAD, quality="poor")).encode(), "poor"),
    (json.dumps(dict(PAYLOAD, ear_closed=0.26)).encode(), "too close"),
])
def test_parse_reject(body, reason):
    with pytest.raises(ValueError, match=reason):
        parse_phone_calibration(body)


def make_drowsy(tmp_path):
    drowsy = Drowsiness.__new__(Drowsiness)
    drowsy.profile = DriverProfile(ear_open=0.3, yaw0=15, gaze_h0=0.6)
    drowsy.profile_dir = tmp_path
    drowsy.pipe = SimpleNamespace(adapter=SimpleNamespace(adapted_ear_open=0.4), close=Mock())
    drowsy._new_pipeline = Mock(return_value=object())
    drowsy.calibrated = False
    drowsy.calib, drowsy.banner = object(), ["calibrating"]
    return drowsy


def test_apply_uses_adapted_pi_baseline(tmp_path):
    drowsy = make_drowsy(tmp_path)
    old_pipe, old_profile = drowsy.pipe, drowsy.profile
    drowsy.apply_phone_calibration(PAYLOAD)
    assert drowsy.profile.ear_open == 0.4
    assert drowsy.profile.ear_closed == pytest.approx(0.38 * 0.4)
    assert drowsy.profile.yaw0 == 15 and drowsy.profile.gaze_h0 == 0.6
    assert old_profile.ear_open == 0.3
    assert DriverProfile.load("default", tmp_path) == drowsy.profile
    old_pipe.close.assert_called_once()
    drowsy._new_pipeline.assert_called_once()
    assert drowsy.pipe is drowsy._new_pipeline.return_value
    assert drowsy.calibrated and drowsy.message == "calibrated (phone)"
    assert drowsy.calib is None and drowsy.banner == []


def test_apply_rejection_keeps_pipeline_and_profile(tmp_path):
    drowsy = make_drowsy(tmp_path)
    old_pipe, old_profile = drowsy.pipe, drowsy.profile
    before = asdict(old_profile)
    drowsy.apply_phone_calibration(dict(PAYLOAD, quality="poor"))
    assert drowsy.profile is old_profile and asdict(old_profile) == before
    assert drowsy.pipe is old_pipe
    old_pipe.close.assert_not_called()
    drowsy._new_pipeline.assert_not_called()
    assert not list(tmp_path.iterdir())
    assert drowsy.message == "calibration failed: poor eye signal"


def test_apply_save_failure_keeps_old_profile_and_pipeline(tmp_path, monkeypatch):
    drowsy = make_drowsy(tmp_path)
    old_pipe, old_profile = drowsy.pipe, drowsy.profile
    before = asdict(old_profile)

    def failing_save(self, path):
        raise OSError("disk write error")

    monkeypatch.setattr(DriverProfile, "save", failing_save)
    Drowsiness.apply_phone_calibration(drowsy, PAYLOAD)
    assert drowsy.profile is old_profile and asdict(old_profile) == before
    assert drowsy.pipe is old_pipe
    old_pipe.close.assert_not_called()
    drowsy._new_pipeline.assert_not_called()
    assert not drowsy.calibrated
    assert drowsy.message == "calibration failed: could not save profile"


def test_apply_rebuild_failure_keeps_running(tmp_path):
    drowsy = make_drowsy(tmp_path)
    drowsy._new_pipeline = Mock(side_effect=RuntimeError("pipeline init failed"))
    Drowsiness.apply_phone_calibration(drowsy, PAYLOAD)
    assert drowsy.message == "calibration failed: pipeline init failed"
    assert not drowsy.calibrated


@pytest.fixture
def stream_module():
    pytest.importorskip("cv2")
    import stream
    return stream


def test_submit_latest_snapshot_and_reject(stream_module):
    shared = stream_module.Shared()
    payload = dict(PAYLOAD)
    shared.submit_phone_calibration(payload)
    payload["closed_ratio"] = 0.5
    assert shared.phone_calibration["closed_ratio"] == 0.38
    shared.submit_phone_calibration(payload)
    assert shared.phone_calibration["closed_ratio"] == 0.5
    with pytest.raises(ValueError, match="poor"):
        shared.submit_phone_calibration(dict(PAYLOAD, quality="poor"))
    assert shared.phone_calibration["closed_ratio"] == 0.5
    assert shared.calibration_error is None


@pytest.mark.parametrize("body,code,reason", [
    (b"", 200, None), (json.dumps(PAYLOAD).encode(), 200, None),
    (b"{", 400, "invalid JSON"),
    (json.dumps(dict(PAYLOAD, quality="poor")).encode(), 400, "poor"),
    (b" " * 4097, 400, "too large"),
])
def test_http_calibrate(stream_module, body, code, reason):
    shared = stream_module.Shared()
    handler = stream_module.make_handler(shared).__new__(stream_module.make_handler(shared))
    handler.path = "/calibrate"
    handler.headers = {"Content-Length": str(len(body))} if body else {}
    handler.rfile, handler.wfile = BytesIO(body), BytesIO()
    handler.send_response, handler.send_header, handler.end_headers = Mock(), Mock(), Mock()
    handler.do_POST()
    handler.send_response.assert_called_once_with(code)
    handler.send_header.assert_any_call("Content-Type", "application/json")
    result = json.loads(handler.wfile.getvalue())
    assert result["ok"] is (code == 200)
    assert handler.rfile.tell() <= 4096
    if reason:
        assert reason in result["error"]
        assert shared.calibration_error == result["error"]
        assert shared.phone_calibration is None
    elif body:
        assert shared.phone_calibration == PAYLOAD
        assert shared.calibration_error is None
    else:
        assert shared.calibrate


def test_invalid_submit_keeps_queued_payload(stream_module):
    shared = stream_module.Shared()
    shared.submit_phone_calibration(PAYLOAD)
    assert shared.phone_calibration == PAYLOAD

    handler = stream_module.make_handler(shared).__new__(stream_module.make_handler(shared))
    handler.path = "/calibrate"
    bad_body = b"{"
    handler.headers = {"Content-Length": str(len(bad_body))}
    handler.rfile, handler.wfile = BytesIO(bad_body), BytesIO()
    handler.send_response, handler.send_header, handler.end_headers = Mock(), Mock(), Mock()
    handler.do_POST()
    handler.send_response.assert_called_once_with(400)
    assert shared.phone_calibration == PAYLOAD
    assert shared.calibration_error == "invalid JSON"


@pytest.mark.parametrize("error", [None, "poor eye signal"])
def test_pipeline_consumes_phone_update_and_publishes_status(stream_module, monkeypatch, error):
    import drowsiness

    shared = stream_module.Shared()
    if error:
        with shared.cond:
            shared.calibration_error = error
    else:
        shared.submit_phone_calibration(PAYLOAD)
    source = Mock(size=(640, 480))
    source.read.side_effect = [(object(), 1.0), (None, None)]
    pipe = Mock()
    pipe.roi = SimpleNamespace(out_w=640, out_h=480, rectified=False, rect=None)
    pipe.process.return_value = SimpleNamespace(face=None, baseline={"progress": 1},
                                                behaviours={}, timings_ms={})
    log = Mock()
    log.update.return_value = []
    drowsy = Mock(message="old")
    drowsy.feed.side_effect = lambda *args: {"message": drowsy.message, "ms": 0}

    def apply(payload):
        assert payload == PAYLOAD
        assert not shared.cond._lock._is_owned()
        drowsy.message = "calibrated (phone)"

    drowsy.apply_phone_calibration.side_effect = apply
    monkeypatch.setattr(stream_module, "open_source", lambda *a, **kw: source)
    monkeypatch.setattr(stream_module, "DistractionPipeline", lambda *a, **kw: pipe)
    monkeypatch.setattr(stream_module, "EventLog", lambda *a, **kw: log)
    monkeypatch.setattr(drowsiness, "Drowsiness", lambda *a, **kw: drowsy)
    stream_module.pipeline_loop(stream_module.parse_args(["--drowsiness"]), shared)
    expected = f"calibration failed: {error}" if error else "calibrated (phone)"
    assert shared.status["drowsiness"]["message"] == expected
    assert shared.phone_calibration is None and shared.calibration_error is None
    assert drowsy.apply_phone_calibration.call_count == (0 if error else 1)


def test_pipeline_queued_payload_with_error(stream_module, monkeypatch):
    import drowsiness

    shared = stream_module.Shared()
    shared.submit_phone_calibration(PAYLOAD)
    with shared.cond:
        shared.calibration_error = "invalid JSON"

    source = Mock(size=(640, 480))
    source.read.side_effect = [(object(), 1.0), (None, None)]
    pipe = Mock()
    pipe.roi = SimpleNamespace(out_w=640, out_h=480, rectified=False, rect=None)
    pipe.process.return_value = SimpleNamespace(face=None, baseline={"progress": 1},
                                                behaviours={}, timings_ms={})
    log = Mock()
    log.update.return_value = []
    drowsy = Mock(message="old")
    drowsy.feed.side_effect = lambda *args: {"message": drowsy.message, "ms": 0}

    def apply(payload):
        assert payload == PAYLOAD
        assert not shared.cond._lock._is_owned()
        drowsy.message = "calibrated (phone)"

    drowsy.apply_phone_calibration.side_effect = apply
    monkeypatch.setattr(stream_module, "open_source", lambda *a, **kw: source)
    monkeypatch.setattr(stream_module, "DistractionPipeline", lambda *a, **kw: pipe)
    monkeypatch.setattr(stream_module, "EventLog", lambda *a, **kw: log)
    monkeypatch.setattr(drowsiness, "Drowsiness", lambda *a, **kw: drowsy)
    stream_module.pipeline_loop(stream_module.parse_args(["--drowsiness"]), shared)
    assert shared.status["drowsiness"]["message"] == "calibrated (phone)"
    assert shared.phone_calibration is None and shared.calibration_error is None
    assert drowsy.apply_phone_calibration.call_count == 1
