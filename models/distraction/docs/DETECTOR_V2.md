# Detector v2: one yolo26n for phone / drink / food (2026-10-17)

One Pi-sized detector (yolo26n, 416 px, NCNN `models/det_v2b_416_ncnn_model`) and three rules
(`live.py --mode simple`, the default; `src/rtdms_distraction/simple_rules.py`):

| rule | |
|---|---|
| phone box in >= 60 % of the last 1 s | phone ALERT |
| drink box overlapping the lower face (nose tip .. chin + 0.35 fw), 0.5 s | drinking ALERT |
| food box overlapping the lower face, 0.5 s | eating ALERT |

The ear / mouth crop classifiers and the full rule engine stay in the code (`--mode full`), off
by default.

## Training data (`scripts/build_det_v2.py`, D:/rtdms-data/det_v2/merged_b)

| source | view | boxes | split |
|---|---|---|---|
| SynDD A1 rear view, 69 drivers | IR, mirror camera | auto-labelled (`label_video_boxes.py`) | by driver (`configs/syndd_split.json`) |
| EBDD, 13 drivers | colour, windshield | auto-labelled | by driver |
| Open Images V7 | photos | GT + teacher fills (hand dropped) | Open Images splits |
| Roboflow DMS_Project v2 (CC BY 4.0) | IR + colour DMS | phone, drinking, eating | Roboflow's (image-level) |
| Roboflow ADMS_FINAL_3 v1 (CC BY 4.0) | colour in-car | using iphone, drinking | Roboflow's (image-level) |

- **Auto-labels**: yolo26m on a zoomed driver crop plus a tight face crop (TTA) for phone calls
  and drinking; a box is kept only if it agrees with the segment label (phone near the face for
  calls, drink / food near the mouth); positive frames with no agreeing box are dropped, normal /
  hand-on-head frames are phone-free background. Checked on contact sheets
  (`D:/rtdms-data/runs/label_checks/det_v2_*`).
- **SynDD texting**: some drivers hold the phone below the frame (no box possible).
- **Roboflow filters**: images with a box larger than 12 % (phone, food) / 8 % (drink) of the
  image are dropped (DMS_Project "drinking" mixes object and whole-action boxes), and images
  with no phone / drink / food box are dropped (seatbelt / yawn shots show unlabelled phones).
- **IR + colour**: 7,010 gray copies of colour train images. **Occlusion**: 7,913 copies of
  phone images with a real hand (Open Images GT hands, brightness-matched) over 30-60 % of the
  phone. Train: 53.9k images.
- yolo26n from COCO, 7 epochs on the set without Roboflow, then 35 more on the full set
  (`det_v2a_416` -> `det_v2b_416`), imgsz 416, batch 64, colour augmentation.

## Results

**Phone found per frame, 10 held-out SynDD drivers** (1 frame/s of each annotated segment,
conf 0.25; the same frames for every model):

| model | phone R ear | phone L ear | phone in hand | normal (false) | hand on head (false) |
|---|---|---|---|---|---|
| stock yolo26n @416 | 2.9 % | 3.5 % | 4.2 % | 0 % | 0 % |
| v1_416 | 7.1 % | 0.9 % | 9.8 % | 0 % | 8.4 % |
| v1_512 | 26.8 % | 34.5 % | 31.1 % | 21.7 % | 28.5 % |
| teacher yolo26m @1280 | 82.4 % | 79.2 % | 24.1 % | 6.9 % | 10.4 % |
| **det_v2b @416** | **71.5 %** | **91.6 %** | 23.1 % | **0 %** | **0.7 %** |

Phone in hand is low for every model, the teacher included: in SynDD's mirror view many
drivers text with the phone below the frame.

**Per class, test split, IoU 0.5, conf 0.25** (labels partly teacher-made, see above):

| test set | class | n | stock P / R | det_v2b P / R | det_v2b AP50 |
|---|---|---|---|---|---|
| SynDD (10 drivers) | phone | 1141 | 0.71 / 0.06 | **0.77 / 0.67** | 0.78 |
| SynDD | drink | 45 | 0 / 0 | 0.83 / 0.53 | 0.78 |
| EBDD (2 drivers) | phone | 224 | 0.91 / 0.30 | 0.87 / 0.63 | 0.75 |
| EBDD | food | 20 | 0 / 0 | 0.72 / 0.65 | 0.61 |
| Open Images | phone | 489 | 0.94 / 0.71 | 0.89 / 0.87 | 0.92 |
| Open Images | drink | 1905 | 0.83 / 0.39 | 0.74 / 0.46 | 0.56 |
| Open Images | food | 1493 | 0.86 / 0.15 | 0.68 / 0.38 | 0.48 |
| DMS_Project | phone / drink / food | 140 / 578 / 129 | | 0.90-0.95 / 0.95-0.99 | 0.97-0.99 |

DMS_Project's split is image-level (frames of the same clips on both sides), so its numbers are
inflated by near-duplicates; SynDD and EBDD are split by driver and are the ones to trust.
NCNN matches the PyTorch weights on the SynDD test set (phone P 0.766 / R 0.667).

**Full pipeline, simple mode, held-out driver 20507**: left-ear call 12 s -> phone in 360 / 360
frames, ALERT 342; right-ear call 16 s -> phone in 182 / 480 frames, ALERT 183 frames. One 4 s
"phone call right" span (video 5, 328-332 s) shows no phone call at all on the frames (label
error in SynDD).

**Speed** (laptop CPU, NCNN, 1280x720 frames, simple mode): 33 FPS, detector 22 ms + face mesh
8 ms per frame.

## Reproduce

```bash
python scripts/label_video_boxes.py syndd --src D:/rtdms-data/public/syndd/A1 \
    --split-file configs/syndd_split.json --out D:/rtdms-data/det_v2/syndd --workers 4
python scripts/label_video_boxes.py ebdd --src D:/rtdms-data/raw/ebdd/x --out D:/rtdms-data/det_v2/ebdd
python scripts/build_det_v2.py --out D:/rtdms-data/det_v2/merged_b \
    --yolo D:/rtdms-data/det_v2/syndd --yolo D:/rtdms-data/det_v2/ebdd \
    --roboflow D:/rtdms-data/public/roboflow/dms_project \
    --roboflow D:/rtdms-data/public/roboflow/adms_final_3
python scripts/train.py --data D:/rtdms-data/det_v2/merged_b/data.yaml --imgsz 416 \
    --name det_v2b_416 --epochs 35 --look color --weights <det_v2a_416 last.pt or models/yolo26n.pt>
python scripts/export_ncnn.py --weights D:/rtdms-data/runs/det_v2b_416/weights/best.pt \
    --name det_v2b_416 --imgsz 416
```
