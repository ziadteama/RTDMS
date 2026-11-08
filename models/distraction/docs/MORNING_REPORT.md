# Morning report — overnight run 2026-10-11

Branch `phone/distraction-baseline` (pushed). Nothing was sent or downloaded. No datasets or
recordings were deleted, and the webcam was not opened.

## What finished

| Step | Status |
|---|---|
| Crop rebuild (3MDAD front view + Open Images, crops stored at 160 px) | done |
| Per-driver ear-phone sheet | done, **0 of 50 drivers flagged** (after the passenger fix below) |
| Mouth test sheet for your hand-check (200 crops + CSV) | done, see "What I need from you" |
| Ear and mouth classifiers trained, exported to NCNN, loaded by the live pipeline | done |
| `bench_live.py` on S01, all three setups | done |
| Crop size study (96 / 128 / 160, chosen on **val** drivers only) | done: ear **160**, mouth **96** |

Every training run passed on its first attempt; nothing needed a retry.

**Not done:**
- EBDD: waiting for the password.
- YawDD: not placed in `data/public/yawdd` yet.
- SynDD: not received yet.
- Webcam / guided run: left for you, as asked.
- Pi run with the classifiers: Pi work is parked.

## Held-out drivers: per-class precision / recall

The split is by driver, 70 / 15 / 15. The 3MDAD test drivers are s8, s10, s11, s17, s25,
s26, s28 and s36. Results are scored through the NCNN runtime that `live.py` uses.

**Ear classifier, 160 px (in use)**, test drivers:

| class | n | precision | recall |
|---|---|---|---|
| phone | 433 | 0.963 | 0.905 |
| hand_no_phone | 71 | 0.568 | 0.761 |
| none | 866 | 0.941 | 0.943 |

**Mouth classifier, 96 px (in use)**, **CLIP-labelled test set** (the drink labels are not
hand-checked yet):

| class | n | precision | recall |
|---|---|---|---|
| drink | 163 | 0.887 | 0.865 |
| food | 15 | 0.933 | 0.933 |
| none | 326 | 0.930 | 0.942 |

Food is too small to mean much: it comes only from Open Images, with 15 test crops and 4 val
crops.

**Size study.** The F1 values are means over classes: all three classes for the ear, drink and
none only for the mouth (val has just 4 food crops). The choice was made on val; test is shown
for information only.

| model | val F1 | test F1 | phone / drink test P/R |
|---|---|---|---|
| ear 96 | 0.884 | 0.821 | 0.916 / 0.905 |
| ear 128 | 0.899 | **0.880** | 0.950 / 0.912 |
| **ear 160 (chosen)** | **0.910** | 0.842 | 0.963 / 0.905 |
| **mouth 96 (chosen)** | **0.947** | 0.906 | 0.887 / 0.865 |
| mouth 128 | 0.939 | 0.910 | 0.932 / 0.834 |
| mouth 160 | 0.939 | 0.895 | 0.948 / 0.785 |

**Caution on the ear.** 160 won on val, but 128 is better on test. The gap is almost all
hand_no_phone precision (0.57 at 160 against 0.77 at 128), measured on only 64 val and 71 test
crops. Phone P/R is about the same at both sizes. I kept the val choice, as the rule says, and
kept `models/ear_cls_128_ncnn_model`. Switching back is two lines in
`configs/profiles/laptop_webcam.yaml`.

Contact sheets (green = correct, red = wrong; about 30 held-out crops per class):
`D:/rtdms-data/runs/{ear_cls_160,mouth_cls_96}/test_contact_sheet.jpg`.

## FPS per setup (laptop, S01 recording, 1280×720)

`python scripts/bench_live.py data/recordings/S01_guided_day_20261010T152706Z.mp4`

This runs the same pipeline and overlay as `live.py` on frames from the file; camera capture
is not timed. Each setup loads only its own models.

| setup | fps | ms/frame | detect | face mesh | hands | pose | crop classifiers |
|---|---|---|---|---|---|---|---|
| hands | 16.5 | 60.7 | 37.5 | 9.9 | 10.2 | – | – |
| hands+pose | 15.8 | 63.2 | 33.7 | 9.3 | 9.4 | 7.6 | – |
| hands+pose+clf | 12.2 | 81.8 | 37.5 | 10.1 | 9.8 | 8.2 | 12.8 |

The detector is stock yolo26n through NCNN. One classifier call costs about 1.1 ms at 96 px,
1.8 ms at 128 and 2.9 ms at 160 (1 thread). The rest of the 12.8 ms stage is cropping and
resizing.

## Problems found

1. **3MDAD front view (RGB2) is mirrored.** A7 (phone in the right hand) has the phone at image
   right. The ear is now taken from the label plus the flip. The per-driver sheet confirms it
   for all 50 drivers (`D:/rtdms-data/runs/label_checks/ear_phone_per_driver.jpg`, plus `.csv`
   with CLIP scores; the lowest is s12 at 0.80, where the phone sits at the crop's inner edge).
2. **The face tracker locked onto the rear passenger** in some clips (s6, s29), so those crops
   came from the wrong face. Fixed in `build_crops.py`:
   - faces centred right of 0.85 w, or narrower than 0.1 w, are rejected;
   - crops less than 75 % inside the frame are dropped.

   `live.py` has no such guard. A person behind you in the webcam view could be tracked
   instead of you.
3. **Drink labels come from CLIP, not ground truth.** yolo26m, YOLO-World and MediaPipe hands
   all missed most cups at the lips. CLIP ViT-L/14 zero-shot at ≥ 0.97 caught them, and
   lower-scoring frames are dropped, not labelled none. In my own pass over your sheet, about
   13 of the 100 "drink" tiles look doubtful (5, 6, 10, 20, 26, 32, 48, 52, 83, 85, 90, 91, 95:
   face visible, no cup). The "none" tiles look clean. Please judge for yourself.
4. **Phone labels are clip-level.** A few "phone" crops show mostly hair or window, where the
   phone is barely in the crop.
5. **Food has no driver video yet**, only Open Images photos. The food numbers aren't meaningful
   until EBDD arrives.
6. **hand_no_phone is small** (330 3MDAD + 502 Open Images crops). It is the weakest class and
   the one that decided the ear crop size.
7. **The crop classifiers now run every frame**, on the last face for up to 1 s when it is
   hidden. That costs about 3.6 fps on the laptop (15.8 → 12.2).

## What I need from you

1. **Hand-check the mouth test sheet:** `D:/rtdms-data/runs/label_checks/mouth_test_drivers.jpg`
   - The tiles are numbered and listed in `mouth_test_drivers.csv`: 1–100 are labelled drink,
     101–200 none.
   - Send me the numbers that are wrong.
   - I'll fix those labels, create `D:/rtdms-data/crops/mouth/HAND_CHECKED`, and re-score. The
     "CLIP-labelled" mark then drops from the results.
2. **Guided run with all three setups:**
   ```bash
   python scripts/live.py --guided
   ```
   - It uses the laptop_webcam profile and loads ear 160 and mouth 96 automatically.
   - It writes `reports/live_<utc>.md`, which compares the setups.
   - If hand-at-ear false alarms show up, I'd switch the ear model back to 128 (see the
     caution above).
3. **Still waiting on:** the EBDD password (from the author), YawDD placed in
   `data/public/yawdd`, and SynDD access.
