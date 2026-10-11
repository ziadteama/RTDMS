# Training and test data

Decision (2026-10-10): **no self-recorded training data**. The detector is trained on public
datasets made to look like our camera. Our own clips are TEST data only: the developer's S01
webcam clip, and the one-time in-car session (`IN_CAR_TEST_PROTOCOL.md`).

All datasets and derived images live under `configs/data.yaml -> root` (`D:/rtdms-data`, C: is
nearly full), never in git.

> **2026-10-11: current target is the laptop webcam in colour** (`configs/data.yaml: look:
> color`). New conversions and fine-tunes use colour; fisheye geometry and the IR look are off
> (blur, brightness / contrast, noise, JPEG and occlusion stay). The v1 models below were
> trained before this change, on the grayscale IR look.

### Crop classifiers (ear: phone / hand_no_phone / none; mouth: drink / food / none)

`scripts/build_crops.py` crops front-view driver video with the same face mesh and crop
functions as `live.py`, split by driver within each dataset (70 / 15 / 15), then
`scripts/train_crop_classifier.py --kind ear|mouth` trains YOLO26n-cls at 128 px in colour.

- **3MDAD front view** (Kinect 2 = `Day-RGB2`, 50 drivers, day RGB only; the depth, IR and side
  view were deleted). The frames are **mirrored**: on contact sheets A7 (phone, right hand)
  always has the phone at image right, i.e. landmark 454, and A8 at 234. The pose wrist could
  not pick the ear (phone ear 0.6–1.5 fw, other ear 1.1–1.7 fw from a wrist), so the ear comes
  from the label plus the mirroring. A2 hair / makeup -> hand_no_phone where a wrist is within
  0.9 fw of an ear. A13 / A14 drinking -> drink only while **CLIP ViT-L/14 zero-shot** scores
  the mouth region >= 0.97 drinking: yolo26m (COCO), YOLO-World and MediaPipe hands missed most
  cups at the lips, CLIP caught nearly all and scored smoking crops mostly < 0.6. A16 smoking
  is a mouth "none" hard negative.
- The mesh runs on every frame (its face search assumes live frame rate); crops are saved
  every 0.15 s. A face hidden by a cup or phone is held for 1 s, as in `live.py`.
- Per-driver check sheet (`scripts/crop_sheets.py ear-phone`): the mirror mapping held for
  every driver whose face was tracked, but for some clips (s6, s29) the tracker had locked onto
  the **rear passenger** at the right image edge. Faces centred right of 0.85 w or narrower
  than 0.1 w are now rejected (the cropper searches again), and crops less than 75 % inside
  the frame are dropped (`--min-in`).
- **EBDD**: downloaded, encrypted; waiting for the password from the author. Then phone ear =
  where the wrist is, eating -> food while the wrist is at the mouth (check sheets first).
- **Open Images**: hand-at-face -> ear hand_no_phone; food within 0.15 fw of the lips -> mouth
  food (contact sheet ~30/36 eating), plus as many no-food faces -> mouth none.
- **State Farm and AUC: not used** (passenger-side view).
- **3MDAD is not used for the ear classifier** (2026-10-11, `NO_EAR` in `build_crops.py`):
  its RGB2 camera sits low on the dashboard below the mirror and sees the face at
  30-45 deg, so the phone is visible from the side. From a mirror-mounted camera the
  phone hides behind the hand (live: P(phone) 0.00). The ear classifier is off until a
  frontal phone source exists (EBDD). 3MDAD stays in the mouth classifier.
- **Mouth classifier off as well (2026-10-11).** Per segment on the S01 webcam recording,
  share of frames with P >= 0.6 (v1 = before, v2 = with the hand-at-face negatives below):

  | segment | food v1 | food v2 | drink v1 | drink v2 |
  |---|---|---|---|---|
  | drinking | 48 % | 1 % | 0 % | 0 % |
  | eating | 0 % | 37 % | 0 % | 0 % |
  | phone in hand | 0 % | 26 % | 0 % | 0 % |
  | nod / turn | 3 % | 32 % | 0 % | 0 % |
  | talking | 0 % | 8 % | 0 % | 0 % |
  | normal | 4 % | 6 % | 1 % | 0 % |

  v1 calls the clear cup at the lips "food"; v2 calls a turned bare face "food". Held-out
  3MDAD drivers looked fine (drink P/R 0.89/0.87 v1, 0.83/0.81 v2), so this is the camera
  angle, not the split: 3MDAD's 3/4 dashboard view and Open Images photos do not transfer to a
  frontal camera. Needs frontal driver video (EBDD eating, DMD drinking).
- **Mouth hard negatives**: Open Images hand over the mouth / cheek / chin (GT hand box
  >= 15 % of the mouth window, no phone / drink / food in the image) and 3MDAD A2 hair /
  makeup -> mouth none, kept first when none is capped (live: hand on the cheek gave
  P(food) 0.99).

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
