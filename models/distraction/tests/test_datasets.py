"""Adapters on small synthetic folders that follow each dataset's documented layout."""

import json

import cv2
import numpy as np
import pytest

from rtdms_distraction import datasets as D


def tiny_video(path, seconds=4, fps=10):
    path.parent.mkdir(parents=True, exist_ok=True)
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    for _ in range(seconds * fps):
        w.write(np.zeros((48, 64, 3), np.uint8))
    w.release()


def test_hms():
    assert D.hms("0:01:23") == 83 and D.hms("01:23") == 83 and D.hms("7.5") == 7.5


def test_syndd_rear_rows_with_forward_filled_filenames(tmp_path):
    u = tmp_path / "A1" / "user_id_24026"
    for v in ("Dashboard_user_id_24026_NoAudio_3", "Rear_view_user_id_24026_NoAudio_3"):
        tiny_video(u / f"{v}.MP4")
    (u / "user_id_24026.csv").write_text(
        "Filename,Camera View,Activity Type,Start Time,End Time,Label (Primary),Appearance Block\n"
        "Dashboard_user_id_24026_NoAudio_3,Dashboard,Normal Forward Driving,0:00:00,0:00:10,Class 0,None\n"
        ",,Drinking,0:00:10,0:00:20,Class 1,None\n"
        "Rear_view_user_id_24026_NoAudio_3,Rear view,Normal Forward Driving,0:00:00,0:00:10,Class 0,None\n"
        ",,Drinking,0:00:10,0:00:20,Class 1,None\n"
        ",,Phone Call(right),0:00:20,0:00:30,Class 2,None\n"
        ",,Text (Left),0:00:30,0:00:40,Class 6,None\n"
        ",,Hand on head,0:00:40,0:00:50,Class 15,None\n"
        ",,Adjust control panel,0:00:50,0:01:00,Class 9,None\n", encoding="utf8")
    segs = D.syndd(tmp_path)
    assert all(s.video.name.startswith("Rear_view") for s in segs)
    assert [s.label for s in segs] == ["normal", "drinking", "phone_right_ear", "phone_in_hand",
                                       "neg_hand_on_head"]
    assert segs[2].start_s == 20 and segs[2].end_s == 30
    assert {s.driver for s in segs} == {"syndd_24026"}


def test_syndd_dashboard_only_csv_maps_to_rear_video(tmp_path):
    u = tmp_path / "user_id_11111"
    tiny_video(u / "Rear_view_User_id_11111_NoAudio_5.MP4")
    (u / "user_id_11111.csv").write_text(
        "Filename,Camera View,Activity Type,Start Time,End Time\n"
        "Dashboard_User_id_11111_NoAudio_5,Dashboard,Eating,0:00:05,0:00:15\n", encoding="utf8")
    segs = D.syndd(tmp_path)
    assert len(segs) == 1 and segs[0].label == "eating"
    assert segs[0].video.name.startswith("Rear_view")


def test_dmd_openlabel(tmp_path):
    d = tmp_path / "dmd" / "gA" / "1" / "s1"
    stem = "gA_1_s1_2019-03-08T09;31;15+01;00"
    tiny_video(d / f"{stem}_ir_body.mp4", seconds=4, fps=10)
    doc = {"openlabel": {"actions": {
        "0": {"type": "driver_actions/phonecall_left",
              "frame_intervals": [{"frame_start": 10, "frame_end": 19}]},
        "1": {"type": "driver_actions/radio", "frame_intervals": [{"frame_start": 0,
                                                                     "frame_end": 5}]},
        "2": {"type": "gaze_on_road/looking_road", "frame_intervals": []}}}}
    (d / f"{stem}_rgb_ann_distraction.json").write_text(json.dumps(doc), encoding="utf8")
    segs = D.dmd(tmp_path)
    assert len(segs) == 1
    s = segs[0]
    assert s.label == "phone_left_ear" and s.start_s == pytest.approx(1.0)
    assert s.end_s == pytest.approx(2.0) and s.driver == "dmd_gA1"


def test_yawdd_names(tmp_path):
    for n in ("1-FemaleNoGlasses-Normal", "1-FemaleNoGlasses-Talking", "2-MaleGlasses-Yawning",
              "3-MaleGlasses-Talking&Yawning"):
        tiny_video(tmp_path / "Mirror" / f"{n}.avi", seconds=2)
    segs = D.yawdd(tmp_path)
    assert sorted(s.label for s in segs) == ["neg_normal", "neg_talking", "neg_yawning"]
    assert {s.driver for s in segs} == {"yawdd_1f", "yawdd_2m"}
    assert segs[0].end_s == pytest.approx(2.0, abs=0.2)


def test_driver100_folders(tmp_path):
    for cam in ("Cam1", "Cam4"):
        for cls in ("C1_Drive_Safe", "C5_Talk_Right", "C18_Operate_Radio"):
            f = tmp_path / "Day" / cam / cls / "P012_0001.jpg"
            f.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(f), np.zeros((8, 8, 3), np.uint8))
    st = D.driver100(tmp_path, cams=("Cam4",))
    assert sorted(s.label for s in st) == ["normal", "phone_right_ear"]
    assert {s.driver for s in st} == {"d100_P012"} and {s.view for s in st} == {"Cam4"}


def test_missing_layout_fails_loudly(tmp_path):
    for fn in (D.syndd, D.dmd, D.yawdd):
        with pytest.raises(FileNotFoundError):
            fn(tmp_path)
