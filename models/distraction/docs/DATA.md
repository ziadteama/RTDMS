# Training and test data

Decision (2026-10-10): **no self-recorded training data**. The detector is trained on public
datasets made to look like our camera. Our own clips are TEST data only: the developer's S01
webcam clip, and the one-time in-car session (`IN_CAR_TEST_PROTOCOL.md`).

All datasets and derived images live under `configs/data.yaml -> root` (`D:/rtdms-data`, C: is
nearly full), never in git.

> **2026-10-11: current target is the laptop webcam in colour** (`configs/data.yaml: look:
> color`). New conversions and fine-tunes use colour; fisheye geometry and the IR look are off
> (blur, brightness / contrast, noise, JPEG and occlusion stay). The v1 models below were
> trained before this change, on the grayscale IR look. The ear-crop classifier
> (`build_ear_crops.py` / `train_ear_classifier.py`) uses State Farm (phone / none, split by
> driver) plus Open Images hand-at-face crops (hand_no_phone), in colour.

## Sources

| Source | Status | Role | Licence / access |
|---|---|---|---|
| Open Images V7 (boxes) | downloaded by `build_openimages.py` | train / val / test, all 4 classes | annotations CC BY 4.0; images listed as CC BY 2.0 by their authors |
| YawDD, mirror set | to be placed in `data/public/yawdd` | background frames (train drivers) + false-alarm test (held-out drivers) | research use, on request from the authors |
| SynDD1 / SynDD2, rear-view only | requested | frames per driver -> train/val/test by driver; event-level test | AI City Challenge research licence |
| 100-Driver | requested | same approach; camera to be confirmed | research licence |
| DMD (IR streams) | requested | night / IR test (phone call, texting, drinking) | research licence |
| State Farm, AUC | **not used** | passenger-side view | — |
| S01 webcam clip (developer) | `data/recordings/` | **test only** | own, local |

### Open Images class mapping (`configs/data.yaml`)

phone: Mobile phone · drink: Coffee cup, Mug, Bottle, Drink, Tin can · food: Sandwich, Snack,
Food, Fast food, Hamburger, Hot dog, French fries, Cookie, Doughnut, Banana, Apple, Baked goods ·
hand: Human hand. Leaf food classes are listed because Open Images labels each box with the most
specific class. Tin can was added to drink (cans are common in cars).

Selection: up to 4000 images per class for train (400 for val / test), skipping images whose
boxes for our classes are group boxes or drawings, ranked: object held near a face or touching a
hand first, then any person in the image, then the rest.

## Pipeline

```
build_openimages.py      stream + filter the official CSVs, select, download (max side 1024)
teacher_label.py         fill missing boxes: yolo26m @1280 + TTA (phone, drink, COCO foods),
                         YOLO-World v2-L text prompts (food), MediaPipe Hands (hand);
                         provenance of every box in labels_meta/
review_sample.py make    ~120 stratified images -> review_sample.html (local) -> you mark boxes
review_sample.py score   precision per source x class, missed objects per image
domain_convert.py        head-and-shoulders crop, fisheye geometry, hand occlusion, IR look
extract_frames.py        SynDD / DMD / YawDD / 100-Driver / ours via datasets.py adapters
build_dataset.py         lists + data.yaml; driver-wise split with a leak guard
train.py                 yolo26n from COCO weights, gray, imgsz 416 (+ 512), IRTrainer
eval_detector.py         per-class P / R / AP50 (stock COCO model mapped, vs fine-tuned)
diagnose_detector.py     per-segment detection rate on a guided clip (S01 before / after)
eval_events.py           full pipeline, event-level P / R / F1, false alarms / h, time-to-alert
purge_recordings.py      delete raw recordings whose frames were extracted (confirmation)
```

`run_oiv_pipeline.sh` runs teacher -> convert -> dataset -> train (416, 512) -> export -> evals.

## Teacher choice (measured, 2026-10-10)

The spec named yolo26m + YOLOE / YOLO-World. Each open-vocabulary candidate was scored against
Open Images ground truth on a 40-image train sample (IoU 0.5), as a sanity check before
spending ~1 GPU-hour on the full set:

| Teacher | Class | Setting | Recall vs GT | Unmatched boxes |
|---|---|---|---|---|
| YOLOE-26l-seg | hand | 640, conf 0.30 / 0.10 / 0.05 | 0.04 / 0.11 / 0.25 | 1 / 5 / 13 |
| YOLOE-26l-seg | hand | prompt "hand" only, 1024, conf 0.10 | 0.19 | 12 |
| YOLOE-26l-seg | food | 640, conf 0.10 / 0.05 | 0.20 / 0.40 | 4 / 7 |
| YOLO-World v2-L | food | 640, conf 0.10 / 0.05 | 0.24 / 0.44 | 1 / 8 |
| MediaPipe Hands | hand | min conf 0.3, pad 0.10 | 0.24 | 5 |

Kept: YOLO-World at conf 0.10 for food and MediaPipe Hands for hands (similar recall, fewest
boxes that match nothing; precision matters most for a gap-filler). "Unmatched" is not the
same as wrong: Open Images is not exhaustive, so some are real unlabelled objects. 40 images is
a sanity check, not a measurement; the review sample is the measurement.

Two practical findings: YOLOE is a segmentation model and at 1280 px its per-box masks overflow
an 8 GB GPU; and passing Ultralytics a list of mixed-size photos with TTA at 1280 peaked at
13.5 GB (Windows then spills to system RAM, ~4 s/image). Per-image calls stay under 6.5 GB at
~0.13 s/image, so teacher_label.py predicts one image per call.

## Caveats that affect the numbers

- **Test labels are partly teacher-made.** Open Images is not exhaustively labelled, so val/test
  boxes are ground truth + teacher fills. Detector P/R on that set measures agreement with
  GT-plus-teacher, not with a human-complete labelling; the review sample quantifies the gap.
- **Domain.** Open Images is photos, not cabin video. Conversion approximates our camera; the
  numbers that matter are S01, SynDD rear-view and the in-car session, not Open Images test.
- **Phone is the scarcest class** (all 3,804 usable train images taken; only 94 in val).

## Privacy

Raw recordings stay local and gitignored. `purge_recordings.py` deletes a raw video only after
frames were extracted from it, after you type DELETE; clips never extracted (S01) are untouched.
