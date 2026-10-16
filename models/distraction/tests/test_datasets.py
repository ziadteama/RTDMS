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


def test_syndd_2024_class_numbers_and_loose_filenames(tmp_path):
    """AIC24 A1 layout: generic Activity Type, 'Class <n>' labels, CSV filenames without
    NoAudio and with inconsistent spelling; matched by view kind + block number."""
    u = tmp_path / "A1" / "user_id_13522"
    for v in ("Rear_view_user_id_13522_NoAudio_5", "Rear_view_user_id_13522_NoAudio_7"):
        tiny_video(u / f"{v}.MP4")
    (u / "user_id_13522.csv").write_text(
        "Filename,Camera View,Activity Type,Start Time,End Time,Label (Primary),Appearance Block\n"
        "Dashboard_user_id_13522_5,Dashboard,Distracted Behavior,00:00:11,00:00:31,Class 2,None\n"
        "Rear_view_user_id_13522_5,Rearview,Distracted Behavior,00:00:11,00:00:31,Class 2,None\n"
        "Rear_view_user_id_13522_5,Rearview,Distracted Behavior,00:01:25,00:01:48,Class 8,None\n"
        "Rearview_User_id_13522_7,Rear View,Distracted behavior,00:02:03,00:02:24,Class 14,Hat\n",
        encoding="utf8")
    segs = D.syndd(tmp_path)
    assert [(s.label, s.video.stem[-1]) for s in segs] == [("phone_right_ear", "5"),
                                                           ("neg_hand_on_head", "7")]
    assert segs[0].start_s == 11 and segs[0].end_s == 31 and segs[0].driver == "syndd_13522"


def test_syndd_clips_read_only_their_span(tmp_path):
    u = tmp_path / "user_id_22222"
    tiny_video(u / "Rear_view_user_id_22222_NoAudio_1.MP4", seconds=4, fps=10)
    (u / "user_id_22222.csv").write_text(
        "Filename,Camera View,Activity Type,Start Time,End Time\n"
        "Rear_view_user_id_22222_NoAudio_1,Rear view,Phone Call(left),0:00:01,0:00:03\n"
        ",,Drinking,0:00:03,0:00:03.5\n", encoding="utf8")
    clips = D.syndd_clips(tmp_path)
    assert len(clips) == 1  # the 0.5 s drinking span is below min_s
    c = clips[0]
    assert c.label == "phone_left_ear" and c.source == "syndd"
    assert c.name == "Rear_view_user_id_22222_NoAudio_1_0001000.MP4"
    ts = [t for t, _ in c.frames(0.5)]
    assert ts == pytest.approx([0.0, 0.5, 1.0, 1.5])  # 1 s .. 3 s, relative to the span


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


def test_ebdd_names_and_clip_frames(tmp_path):
    for n in ("AKKAS_CELL_PHONE", "AKKAS_EATING", "TASHRIF_ATTENTIVE", "ZAKARIA_UNATTENTIVE",
              "SOHEL_TEXT"):
        tiny_video(tmp_path / "EBDD_Video_Database" / f"{n}.mp4", seconds=3, fps=10)
    clips = D.ebdd(tmp_path)
    got = {(c.driver, c.label) for c in clips}
    assert got == {("ebdd_akkas", "phone_unknown_ear"), ("ebdd_akkas", "eating"),
                   ("ebdd_tashrif", "normal"), ("ebdd_zakaria", "other_none"),
                   ("ebdd_sohel", "phone_in_hand")}
    ts = [t for t, _ in clips[0].frames(0.5)]
    assert ts[:3] == pytest.approx([0.0, 0.5, 1.0]) and len(ts) == 6


def test_3mdad_front_frame_folders(tmp_path):
    for view in ("RGB1", "RGB2"):
        for s, a in ((6, 7), (6, 13), (31, 8), (31, 9)):
            d = tmp_path / "Day" / view / f"S{s}" / f"AC{a}"
            d.mkdir(parents=True)
            for i in range(12):
                cv2.imwrite(str(d / f"img_{i}.jpg"), np.zeros((8, 8, 3), np.uint8))
    clips = D.mdad3_front(tmp_path)  # RGB2 = front view only; A9 (picture) skipped
    assert sorted((c.driver, c.label) for c in clips) == [
        ("3mdad_s31", "phone_left_ear"), ("3mdad_s6", "drinking"), ("3mdad_s6",
                                                                     "phone_right_ear")]
    assert all("RGB2" in str(c.path) for c in clips)
    assert len(list(clips[0].frames(0.1))) == 4  # every 3rd of 12 frames at 30 fps
