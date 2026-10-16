# Crop classifiers retrained on SynDD rear view (2026-10-16)

Ear (phone / hand_no_phone / none, 160 px) and mouth (drink / food / none, 96 px) crop
classifiers, YOLO26n-cls, 40 epochs, **grayscale**. Scored through the NCNN runtime that
`live.py` uses. Models: `models/{ear_cls_160_syndd,mouth_cls_96_syndd}_ncnn_model`, loaded by
`configs/profiles/laptop_webcam.yaml`.

## Data

| Source | View | Used for |
|---|---|---|
| **SynDD (AIC24 track 3, A1)**, 69 drivers, rear-view mirror camera only | IR, front-right of the driver | ear + mouth, main source |
| EBDD, 13 drivers | windshield, colour -> gray | ear phone, mouth food |
| 3MDAD front view (reused crops) | low dashboard | **mouth only** (not the ear: angle) |
| Open Images (reused crops) | photos | ear hand_no_phone, mouth food / none |

- SynDD fetched with `scripts/fetch_syndd.py` (rear-view MP4s + CSVs only, ~93 GB of the
  ~300 GB A1 zips). The 2024 CSVs carry the activity only as `Class <n>`; the CSV for driver
  79755 is named `user_id_79775.csv`.
- Checked on user_id_13522 before cropping: frames are **not mirrored** (phone call right ->
  image left = landmark 234); face mesh found the face in 98.5 % of 11,880 frames.
- SynDD is infrared, so every crop (all sources) is gray x3 and the live crops are converted
  the same way; otherwise "gray" would separate SynDD from the colour sources.
- Split by driver, 70 / 15 / 15 within each dataset. SynDD split fixed in
  `configs/syndd_split.json` (49 / 10 / 10); test drivers 20507, 25077, 30932, 35418, 53307,
  57207, 60167, 60768, 83323, 99635.
- Labels: SynDD phone call right / left -> phone at that ear; drinking -> drink while CLIP
  ViT-L/14 says drinking (>= 0.97); eating -> food while the pose wrist is at the mouth; hand
  on head -> hand_no_phone at the wrist's ear; texting / talking / yawning / singing -> none.

| | train | val | test |
|---|---|---|---|
| ear phone / hand_no_phone / none | 7240 / 3088 / 14480 | 1459 / 513 / 2918 | 1536 / 594 / 3072 |
| mouth drink / food / none | 1434 / 624 / 2868 | 452 / 72 / 904 | 269 / 103 / 538 |

## Held-out SynDD drivers (10)

**Ear, 160 px**

| class | n | precision | recall |
|---|---|---|---|
| phone | 1449 | 0.983 | 0.867 |
| hand_no_phone | 578 | 0.978 | 0.827 |
| none | 2709 | 0.904 | 0.991 |

Macro F1 0.921 (all test drivers, all sources: 0.917; val 0.981). Nearly every error is a
phone or hand called "none" (191 + 93 of 4736); 15 none crops were called phone. On the
contact sheet the missed phones are mostly hidden behind the hand or hair in dark crops.

**Mouth, 96 px**

| class | n | precision | recall |
|---|---|---|---|
| drink | 109 | 1.000 | 0.771 |
| food | 75 | 0.683 | 0.573 |
| none | 190 | 0.815 | 0.974 |

Macro F1 0.794 (all test drivers: 0.795; val 0.797). Food is the weakest class: 75 test crops,
most from one driver with a hand pressed to the mouth (food vs none is often "hand at the
mouth" either way). Drink labels are CLIP-made, not hand-checked.

Contact sheets (green = correct, red = wrong): `D:/rtdms-data/runs/{ear_cls_160_syndd,
mouth_cls_96_syndd}/test_contact_sheet_syndd.jpg` (all sources: `test_contact_sheet.jpg`).

## Caveats

- SynDD is IR, our webcam is colour: gray conversion removes colour, not the IR look (skin and
  sunglasses look different under IR). The webcam test is the real check.
- The crop size (160 / 96) was kept from the 2026-10-11 size study, not re-chosen.
- Pi cost not measured for these models (same architecture and sizes as before).

## Reproduce

```bash
python scripts/fetch_syndd.py --rclone <rclone.exe>               # needs the gdrive remote
python scripts/build_crops.py --syndd D:/rtdms-data/public/syndd/A1 \
    --split-file configs/syndd_split.json --ebdd D:/rtdms-data/raw/ebdd/x \
    --reuse crops:3mdad,openimages --no-openimages --grayscale --store-size 160 \
    --workers 6 --out crops_v2
python scripts/train_crop_classifier.py --kind ear --imgsz 160 --crops crops_v2 --grayscale \
    --tag syndd --report-source syndd
python scripts/train_crop_classifier.py --kind mouth --imgsz 96 --crops crops_v2 --grayscale \
    --tag syndd --report-source syndd
```

(This run cropped SynDD in batches while it downloaded and merged them with `--reuse`; the
single command above gives the same split.)
