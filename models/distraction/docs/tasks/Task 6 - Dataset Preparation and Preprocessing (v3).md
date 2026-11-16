# Task 6: Dataset Preparation and Preprocessing (version 3)

**Project:** Real-Time Driver Monitoring System (RTDMS)
**Scope:** face monitoring, and phone / drink / food (distraction) detection
**Prepared by:** Youssef Medhat
**Date:** November 2026
**Programme:** B.Sc. Graduation Project, Computer Engineering, AASTMT

> Version 3 replaces version 2, which is kept unchanged. It lists each model and data choice in
> order, why it was made, and the numbers behind it.

## 1. Summary

- **Camera:** IR NoIR 160° at the centre rear-view mirror, on a Raspberry Pi 5.
- **Face:** MediaPipe face mesh + EAR rules. Eye state on CEW: F1 0.945, accuracy 94.6 %.
- **Calls and texting:** action classifier with ear and lap phone checks.
  - F1 0.929 for calls.
  - Phone-use F1 0.805, vs 0.543 for the old box detector.
  - Runs on the Pi.
- **Drinking:** hand-at-mouth crop model (IR-4).
  - 18 / 20 caught, F1 0.878, under 2 false alarms per hour.
  - Meets the target, but is not on the Pi yet.
- **Eating:** experimental only: 13 / 19 caught, F1 0.634. Does not meet the target.
- **The Pi currently gives no drinking or eating alerts** (section 6).

Target: at least 85 % caught (F1 ≥ 0.85) and at most 5 false alarms per hour.

## 2. Sequence of choices

### Face model

1. **MediaPipe face mesh + EAR / PERCLOS rules.**
   - *Why:* the model is pre-trained and small (0.6 M parameters), so it runs on the CPU and
     leaves the AI HAT free.
   - *Result on CEW (1,696 test photos):* F1 0.945, accuracy 94.6 %, 5.1 % false alarms,
     5.1 ms per frame.
   - *Result on the Pi:* 30 fps (the camera's limit), 13.5 ms per frame.
   - The eye-closure alert was set to 1.5 s instead of the planned 2–3 s, to warn earlier.
2. **Compared with two other eye-state models** on the same CEW test set.
   - Haar cascades: F1 0.817.
   - YuNet + eye-state CNN trained on MRL Eye: F1 0.933.
   - *Decision:* keep MediaPipe + EAR. It is the most accurate and the fastest.
3. **Robustness check** (CEW test, damaged images). F1 stays above 0.85 in every case:
   - gray (IR-like) 0.945;
   - dark 0.916;
   - blur 0.900;
   - low resolution 0.896;
   - noise 0.895;
   - heavy JPEG 0.877.

### Phone, drink and food

1. **Ready COCO detector (YOLOv8n), no training.**
   - *Why:* to test the rules before collecting any data.
   - *Result:* a 25× larger model (YOLO11x) found the phone in 45 of 210 frames, vs 38 of 210
     for YOLOv8n. So the model was kept small and trained on in-car data instead.
2. **Ready State Farm classifier** (version 1 of this report).
   - *Why:* weights were available with no training.
   - *Dropped:* State Farm is colour, filmed from the passenger side. Our camera is IR at the
     mirror.
3. **YOLO26n detector trained on Open Images**, with photos converted to look like our camera.
   - *Result:* phone F1 0.825 on Open Images, but **0 %** of phone-at-ear frames found on a real
     webcam clip.
   - *Lesson:* photos do not transfer; in-car video is needed.
4. **Ear and mouth crop classifiers on 3MDAD.**
   - *Result:* phone F1 0.933 on held-out 3MDAD drivers, but 0.00 live.
   - *Dropped:* 3MDAD's camera is low on the dashboard and sees the phone from the side. From the
     mirror, the hand hides it.
5. **SynDD becomes the main dataset.**
   - *Why:* its camera sits at the rear-view mirror, like ours.
   - *Data:* 69 drivers, split by driver 49 / 10 / 10; 18,318 auto-labelled frames.
6. **Detector v2: five sources merged** to 53,889 training images.
   - *Result (det_v2b):* phone F1 0.717; phone at the ear found in 71.5 % / 91.6 % of frames.
7. **det_v2d: gray-only images, 512 px, thresholds chosen on validation drivers.**
   - *Why:* to match the IR camera and cut false alarms.
   - *Result:* validation phone false alarms fell from 36.1 to 5.2 per hour. Test drivers: calls
     80 % / 100 %, drinking 90 %, 0 false alarms per hour. **Became the release model.**
   - Eight other ideas did not beat it. Extra SynDD camera views, for example, raised false
     alarms to 24.1 per hour.
   - A head-down + wrist-low rule raised texting from 36.6 % to 41.5 %.
8. **Test on unseen data.**
   - *Result:* 3MDAD 80–92 % of calls.
   - DAD (real IR): 69 false phone alarms per hour, because the steering wheel was read as a
     phone.
9. **Live on the Pi: near-ear calls missed.**
   - *Result:* median phone score 0.18 at the near ear vs 0.63 at the far ear. The hand hides the
     phone.
   - A lower near-ear threshold reached only 90 % at +3.4 false alarms per hour.
10. **Action classifier + phone checks (v2).**
    - *What:* it classifies what the driver is doing from an upper-body crop, then confirms a
      phone at the ear (calls) or in the lap (texting, lap check AUC 0.84). 3MDAD moved to
      training (35 drivers) for its near-ear examples.
    - *Result, same clips as det_v2d:* phone-use F1 **0.805 vs 0.543**, false alerts 24 vs 112.
    - Rejected along the way: a larger model (about 3× slower, not better) and a smoking class
      (false alarms 7 → 7).
    - **Runs on the Pi.**
11. **Drinking: hand-at-mouth crop model.**
    - *Why:* cup boxes came from a teacher model; checking a hand at the mouth is simpler.
      22,612 crops.
    - *Kept:* IR-3 (1,500 phone-in-hand negatives) and IR-4 (+ light camera simulation).
    - *Reverted:* strong camera simulation (false alarms 1.09 → 3.26 per hour) and all 5,310
      phone negatives (recall 14 → 12 of 15).
    - *Result (IR test):* F1 **0.878 vs 0.735** for the old detector. Same 18 / 20 caught, but
      3 false alerts instead of 11.
12. **Eating.**
    - Object boxes failed: only 3 SynDD training frames show food. A hand-to-mouth + chewing
      rule caught 0 / 19.
    - A temporal model (GRU) on hand-at-mouth crops reaches F1 0.634 (13 / 19 caught,
      10.15 false alarms per hour). Yawning is the main error. Experimental.

## 3. Datasets

| Dataset | IR / RGB | Size | Classes | Used / dropped | Reason |
|---|---|---|---|---|---|
| SynDD A1, mirror view | gray (monochrome daylight, by pixel check) | 69 drivers, 18,318 labelled frames | calls, texting, drinking, eating, normal, look-alikes | **Used (main)** | Same camera position as ours |
| SynDD dashboard / side views | gray | 20 drivers | same | Dropped | Phone false alarms 5.2 → 24.1 / h |
| SynDD A2 | gray | 15 or 10 drivers (two sources disagree) | no labels | Dropped | Pseudo-labels too noisy |
| Open Images V7 | RGB photos | 16,996 photos | phone, drink, food | Used | Object appearance |
| Roboflow DMS_Project | IR + RGB | 10,198 images | phone, drinking, eating | Used | Driver-camera boxes |
| Roboflow ADMS_FINAL_3 | RGB | 2,698 images | phone, drinking | Used | In-car boxes |
| EBDD | RGB → gray | 13 drivers, 2,093 frames | calls, texting, eating | Used | Driver video with eating |
| 3MDAD front | RGB → gray | 50 drivers, 650 clips | 16 actions | Used | Test for det_v2d; training (35 drivers) for v2 |
| DAD | **real IR** | 3 drivers, 66 min normal driving | calls, texting, drinking | Used, test only | Only real-IR test video |
| CEW | RGB faces | 2,423 photos (1,192 closed, 1,231 open) | eyes open / closed | Used | Face-model tuning and test |
| MRL Eye | IR eye crops | 84,898 images, 37 people | eyes open / closed | Used | Comparison eye-state CNN |
| State Farm | RGB | 22,424 images | 10 classes | Dropped | Passenger-side view |
| AUC | RGB | about 44 drivers | 10 classes | Not used | Passenger-side view |
| Drive&Act | NIR | 15 drivers | many | Not used | Labels missing |
| DMD, 100-Driver | IR + RGB | — | many | Not used | Never received |

CEW, MRL Eye and the State Farm, DMS_Project and ADMS_FINAL_3 counts come from the version 2
Task 6 and Task 7 reports. The original CEW and MRL Eye files were lost in a PC reset.

## 4. Data preparation

- **Splits:** always by driver or person, so no test person appears in training.

  | Dataset | Train | Validation | Test |
  |---|---|---|---|
  | SynDD | 49 drivers (13,385 frames) | 10 (2,534) | 10 (2,399) |
  | 3MDAD (v2) | 35 drivers | — | 15 drivers |
  | DAD | — | — | 3 drivers |
  | CEW | 727 photos for tuning | — | 1,696 photos (834 closed, 862 open) |
  | MRL Eye | 58,636 images, 24 people | 13,490, 5 people | 12,772, 8 people |

  Thresholds are chosen on validation (or tuning) data only.
- **Detector set:** 53,889 train / 6,557 val / 4,780 test images.
  - Training boxes: phone 30,193, drink 47,605, food 24,786.
  - Training includes 7,010 gray copies and 7,913 copies with a hand pasted over the phone.
  - SynDD training frames per action: phone at the ear 4,424, texting 2,803, drinking 409,
    eating 3, normal 1,158, look-alikes 4,588.
- **Labels:**
  - Boxes come from a teacher model (YOLO26m at 1280 px; YOLO-World for food). A box is kept only
    if it matches the action label.
  - Roboflow boxes larger than 12 % of the image (8 % for drinks) are removed.
  - Box format: YOLO (class, x, y, w, h).
- **Preprocessing:**
  - Frames every 0.5 s in actions and 1.5 s in normal driving.
  - All images gray.
  - Detector input 512 px; action crops 224 px; phone and cup crops 128 px with a contrast
    stretch.
  - Face images: CEW faces padded and resized to 400 × 400; MRL eyes 32 × 32 gray.
- **Augmentation:**
  - Detector: mosaic, flip, zoom ±50 %, shift ±10 %, rotate ±5°, brightness ±40 %.
  - IR-4: light camera simulation.
  - Eye CNN: 9 types (flip, rotate ±15°, zoom, shift, light, blur, noise and more).

## 5. Model comparison

**Face (eye state, CEW test, 1,696 photos)**

| Model | Accuracy | F1 | False alarms | Speed | Decision |
|---|---|---|---|---|---|
| **MediaPipe + EAR** | 94.6 % | **0.945** | 5.1 % | 5.1 ms | **Used** |
| YuNet + CNN (MRL Eye) | 93.5 % | 0.933 | 5.7 % | 11.8 ms | Comparison only |
| Haar cascades | 80.7 % | 0.817 | 26.1 % | 9.5 ms | Rejected |

**Frame and box level** (per image)

| Model | Test data | Precision | Recall | F1 | Decision |
|---|---|---|---|---|---|
| YOLO26n, Open Images | Open Images test | 0.82 | 0.83 | 0.825 | Dropped: 0 % on a real clip |
| Ear crop classifier | 3MDAD test drivers | 0.963 | 0.905 | 0.933 | Dropped: 0.00 live |
| Ear crop classifier | SynDD test drivers | 0.983 | 0.867 | 0.921 | Off by default |
| Mouth crop classifier (drink) | SynDD test drivers | 1.000 | 0.771 | 0.871 | Off by default |
| det_v2b (416 px) | SynDD test | 0.77 | 0.67 | 0.717 | Replaced |
| det_v2d (512 px, gray) | SynDD validation | 0.818 | 0.628 | 0.711 | Release model |
| det_v2d INT8 | SynDD validation | 0.831 | 0.629 | 0.716 | Ready for the Pi |

**Alert level** (per event, the way the Pi works)

| Model | Behaviour | Test data | Caught (recall) | Precision | F1 | False alarms / h | Decision |
|---|---|---|---|---|---|---|---|
| det_v2d (release) | phone use | SynDD + 3MDAD + DAD | 98/151 (0.649) | 0.467 | 0.543 | 0 / 14.2 / 79.2 | Replaced by v2 |
| **Action v2** | phone use | same clips | 118/151 (0.781) | 0.831 | **0.805** | 0 / 19.6 / 3.6 | **Runs on Pi** |
| Action v2 | calls only | same clips | 72/74 (0.973) | 0.889 | 0.929 | — | Runs on Pi |
| Action v2 | texting only | same clips | 46/77 (0.597) | 0.697 | 0.643 | — | Runs on Pi |
| det_v2d (release) | drinking | IR test | 18/20 (0.900) | 0.621 | 0.735 | 0 / 8.67 | Replaced |
| **IR-4** | drinking | IR test | 18/20 (0.900) | 0.857 | **0.878** | 1.07 / 1.58 | **Best; not on Pi** |
| Eating GRU | eating | IR test | 13/19 (0.684) | 0.591 | 0.634 | 10.15 | Experimental |

How the alert-level numbers are counted:
- **Precision** = caught events ÷ (caught events + false alerts), using the false alerts listed
  in `REPORT_v2.md` and `ir_report.md`.
- **Phone use:** any phone alert during a phone clip counts as correct.
- **False alarms per hour** are listed per test set: SynDD / 3MDAD / DAD, or SynDD / DAD.

## 6. Current state

- **On the Pi:** face mesh + PERCLOS, and the v2 action classifier for calls and texting, at
  about 30 fps.
- **No drinking or eating alerts on the Pi.**
  - In the running stream, these come only from the det_v2d detector, which is switched off
    (`--no-detect`).
  - Turning it back on drops the stream to about 20 fps and brings back about 79 false phone
    alarms per hour on real IR.
- **New drinking (IR-4) and eating models:** the code is on main, but the Pi is not updated. It
  was unreachable and has no internet.
  - Even after updating, the alerts stay off until the stream is changed to use the new models.
  - The weights are not on GitHub.
- **Next:**
  1. Put IR-4 on the Pi and measure speed.
  2. Record our own drivers with the Pi camera.
  3. Calibrate the fisheye lens.
  4. Get true-IR eating data, or leave eating out.

## Sources

| Section | Files |
|---|---|
| Face, CEW, MRL Eye | Task 6 v2 (Figures 2–3, Tables 2–3) and Task 7 v2 (Table 13, Figures 1–2); `models/face/docs/EVIDENCE.md` |
| Phone steps 1–2 | session record (model comparison); `models/phone/docs/EVIDENCE.md`; Task 7 v2 Table 3 |
| Phone steps 3–8 | `models/distraction/docs/` EVIDENCE, DATA, MORNING_REPORT, SYNDD_RETRAIN, DETECTOR_V2, OVERNIGHT_REPORT |
| Phone step 9 | session record of the live Pi test |
| Phone step 10, phone alert table | `action_v1/REPORT.md`, `REPORT_v2.md` (results and false-alarm list), `DECISIONS.md` |
| Steps 11–12, drinking and eating | `action_v1/ir_report.md`, `ir_log.md`, `HELD_OBJECT.md`, `dataset_inventory.md` |
| Data counts | data-build logs; Task 6 v2 Figures 5–6 |
| Current state | `pi/start_stream.sh`, `action_v1/.gitignore`, `action_v1/ir_report.md` §5 |

F1 values for the frame-level models and all alert-level precision and F1 values are calculated
from the precision, recall and event counts in these files. The full history is in `timeline.md`.
