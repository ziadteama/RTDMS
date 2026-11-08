import json
import math
import shutil

import cv2
import numpy as np
import pytest

from rtdms_distraction.config import (
    CONFIG_DIR,
    load_pipeline_config,
    load_rules_config,
    save_roi_rect,
)
from rtdms_distraction.eventlog import EventLog
from rtdms_distraction.facemesh import (
    POSE_IDS,
    POSE_MODEL,
    FaceAnalyzer,
    pose_from_mediapipe_matrix,
)

# --------------------------------------------------------------------------- config


def test_shipped_configs_load():
    p = load_pipeline_config()
    r = load_rules_config()
    assert p.capture.width == 1296 and p.capture.height == 972
    assert p.detector.class_map["cell phone"] == "phone"
    assert r.levels["phone_in_hand"] == "warning"


def test_unknown_key_is_an_error(tmp_path):
    f = tmp_path / "rules.yaml"
    f.write_text("drinking:\n  min_overlapp: 0.2\n")
    with pytest.raises(KeyError, match="min_overlapp"):
        load_rules_config(f)


def test_bad_driver_side(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("driver_side: middle\n")
    with pytest.raises(ValueError):
        load_pipeline_config(f)


def test_save_roi_rect_keeps_comments(tmp_path):
    f = tmp_path / "pipeline.yaml"
    shutil.copy(CONFIG_DIR / "pipeline.yaml", f)
    before = f.read_text()
    save_roi_rect([700, 120, 520, 700], f)
    after = f.read_text()
    assert load_pipeline_config(f).roi.rect == [700, 120, 520, 700]
    assert after.count("#") == before.count("#")


# --------------------------------------------------------------------------- pose


def rot(pitch_down, yaw_right):
    """OpenCV-frame rotation of the face model: pitch about X, then yaw about Y."""
    p, y = math.radians(pitch_down), math.radians(yaw_right)
    rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    # Face turning toward image-right = rotating its -Z (front) toward +X.
    ry = np.array([[math.cos(y), 0, -math.sin(y)], [0, 1, 0], [math.sin(y), 0, math.cos(y)]])
    return ry @ rx


@pytest.mark.parametrize("pitch,yaw", [(0, 0), (20, 0), (-15, 0), (0, 25), (0, -25), (15, 20)])
def test_solvepnp_pose_signs(pitch, yaw):
    K = np.array([[500.0, 0, 320], [0, 500.0, 320], [0, 0, 1]])
    rvec, _ = cv2.Rodrigues(rot(pitch, yaw))
    tvec = np.array([0.0, 0.0, 60.0])
    img, _ = cv2.projectPoints(POSE_MODEL, rvec, tvec, K, np.zeros(4))
    px = np.zeros((478, 2))
    px[list(POSE_IDS)] = img.reshape(-1, 2)
    got = FaceAnalyzer(K).solve_pose(px)
    assert got == pytest.approx((pitch, yaw), abs=1.0)


def test_head_down_moves_nose_down_in_image():
    """Sanity of the sign convention against the image itself."""
    K = np.array([[500.0, 0, 320], [0, 500.0, 320], [0, 0, 1]])
    nose = POSE_IDS.index(1)
    ys = []
    for pitch in (0, 20):
        img, _ = cv2.projectPoints(POSE_MODEL, cv2.Rodrigues(rot(pitch, 0))[0],
                                   np.array([0.0, 0.0, 60.0]), K, np.zeros(4))
        ys.append(img.reshape(-1, 2)[nose, 1])
    assert ys[1] > ys[0]


def test_mediapipe_matrix_signs():
    def m(r):
        out = np.eye(4)
        out[:3, :3] = r
        return out

    a = math.radians(20)
    head_down = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    c, s = math.cos(a), math.sin(a)
    turn_right = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    assert pose_from_mediapipe_matrix(m(head_down)) == pytest.approx((20, 0), abs=1e-6)
    assert pose_from_mediapipe_matrix(m(turn_right)) == pytest.approx((0, 20), abs=1e-6)


# --------------------------------------------------------------------------- event log


def st(level, conf=0.8):
    return {"level": level, "confidence": conf}


def test_event_log_transitions(tmp_path):
    log = EventLog(tmp_path, per_frame=False)
    log.session(source="test")
    assert log.update(0.0, {"drinking": st("none")}) == []
    ev = log.update(1.0, {"phone_in_hand": st("warning"), "drinking": st("none")})
    assert ev[0]["event"] == "start" and ev[0]["level"] == "warning"
    ev = log.update(3.0, {"phone_in_hand": st("alert")})
    assert ev[0]["event"] == "level" and ev[0]["from"] == "warning"
    ev = log.update(4.5, {"phone_in_hand": st("none")})
    assert ev[0]["event"] == "end" and ev[0]["duration_s"] == 3.5 and ev[0]["peak_level"] == "alert"
    log.update(5.0, {"eating": st("warning")})
    log.close(6.0)
    lines = [json.loads(x) for x in log.path.read_text().splitlines()]
    assert [x["event"] for x in lines] == ["session_start", "start", "level", "end", "start",
                                           "end", "session_end"]
    assert lines[-2]["reason"] == "session_end"
