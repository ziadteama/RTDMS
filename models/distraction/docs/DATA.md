# Training and test data

Decision (2026-10-10): **no self-recorded training data**. The detector is trained on public
datasets made to look like our camera. Our own clips are TEST data only: the developer's S01
webcam clip, and the one-time in-car session (`IN_CAR_TEST_PROTOCOL.md`).

All datasets and derived images live under `configs/data.yaml -> root` (`D:/rtdms-data`, C: is
nearly full), never in git.

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
                         YOLOE-26l text prompts (food, hand); provenance in labels_meta/
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
