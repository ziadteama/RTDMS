# Task 6: Dataset Preparation and Preprocessing (version 3)

**Project:** Real-Time Driver Monitoring System (RTDMS)
**Scope:** face monitoring, phone / drink / food (distraction) detection, and heart rate / HRV
**Prepared by:** Youssef Medhat, Omar Deyaa (face and distraction models), Ziad Teama (heart rate / HRV)
**Date:** November 2026
**Programme:** B.Sc. Graduation Project, Computer Engineering, AASTMT

> Version 3 replaces version 2, which is kept unchanged. The report has three parts, one per
> model. Each part lists the choices in order, why each was made, what was dropped and why, the
> data used, and the results.

## Summary

| Model | What runs now | Key result | Status |
|---|---|---|---|
| **1. Face** (drowsiness, looking away) | MediaPipe face mesh + EAR / PERCLOS rules | Eye state on CEW: F1 0.945, accuracy 94.6 %; 30 fps on the Pi | On the Pi |
| **2. Phone, drink, eat** | Calls and texting: action classifier + ear / lap phone checks | Phone-use F1 0.805 (old detector 0.543); calls F1 0.929 | On the Pi |
| | Drinking: hand-at-mouth crop model (IR-4) | 18 / 20 caught, F1 0.878, under 2 false alarms per hour | Ready, **not on the Pi** |
| | Eating: temporal model (GRU) | 13 / 19 caught, F1 0.634, 10.15 false alarms per hour | Experimental |
| **3. Heart rate / HRV** | Garmin watch beat intervals → HRV features → fatigue score | Heart-rate error 0.51 bpm vs ECG; fatigue model AUROC 0.545 | HR works; fatigue experimental |

Targets: vision at least 85 % caught (F1 ≥ 0.85) and at most 5 false alarms per hour; heart rate
error at most 3 bpm.

**The Pi currently gives no drinking or eating alerts.** The reason is in Part 2, section 2.5.

## Part 1: Face model

### 1.1 Choices, in order

1. **One MediaPipe face mesh + simple rules** (EAR, blinks, PERCLOS, head pose, gaze).
   - *Why:* the model is pre-trained, so no face training data is needed. It is small (0.6 M
     parameters), so it runs on the CPU and leaves the AI HAT free.
   - *Result:* one face mesh uses about one laptop core. On the Pi it uses 73 % of one core
     (21 % of the whole Pi). So the face model alone does not need the AI HAT.
2. **Alert after 1.5 s of closed eyes**, not the planned 2–3 s.
   - *Why:* normal blinks last 100–400 ms. Sleep-deprived blinks last about 586 ms. Microsleeps
     start above 500 ms. 2–3 s is too late to warn.
   - *Check:* normal blinking gives PERCLOS 6.25 % over 60 s, well under the 15 % alarm level.
3. **Head-pose gate:** eye closure is ignored when the head turns more than 30°.
   - *Why:* turning the head distorts EAR. Looking at the gear stick would otherwise read as
     closed eyes.
4. **Gaze only as "on road / off road"**, not as gaze zones.
   - *Why:* geometry reaches 68.76 % on 7 gaze zones, vs 95.18 % for a CNN. It is good enough for
     a yes / no "looking away" check, but not for zones.
5. **Tested on CEW against two other eye-state models** (1,696 test photos).
   - MediaPipe + EAR: **F1 0.945**, 5.1 ms per frame. Kept.
6. **Robustness check:** F1 stays above 0.85 on damaged images: gray (IR-like) 0.945, dark 0.916,
   blur 0.900, low resolution 0.896, noise 0.895, heavy JPEG 0.877.
7. **On the Pi: LiteRT runtime** instead of the full MediaPipe package.
   - *Why:* MediaPipe does not install on the Pi's Python 3.13. LiteRT runs the same model files.
   - *Result:* 30 fps (the camera's limit), 13.5 ms per frame, 133 MB of memory.

### 1.2 Dropped and why

| Option | Why it was dropped | Numbers |
|---|---|---|
| Haar cascades (eye state) | Too many false alarms | F1 0.817, 26.1 % false alarms, vs 5.1 % for MediaPipe |
| YuNet face detector + eye-state CNN (trained on MRL Eye) | Slightly less accurate, more than twice as slow, needs a second model | F1 0.933 vs 0.945; 11.8 ms vs 5.1 ms per frame |
| 2–3 s eye-closure alert (Project 1 plan) | Too late: microsleeps start above 0.5 s | Alert set to 1.5 s |
| Gaze zones | Geometry is not accurate enough for zones | 68.76 % (geometry) vs 95.18 % (CNN) on 7 zones |
| Full MediaPipe package on the Pi | Does not install on the Pi's Python 3.13 | Replaced by LiteRT (same model, 13.5 ms) |
| UTA-RLDD, DG-Unicamp tests | Not done yet; planned | — |

### 1.3 Data

| Dataset | IR / RGB | Size | Classes | Used for |
|---|---|---|---|---|
| CEW | RGB face photos, 100 × 100 | 2,423 (1,192 closed, 1,231 open) | eyes open / closed | Tuning thresholds (727 photos) and testing (1,696: 834 closed, 862 open) |
| MRL Eye | IR eye crops | 84,898 images, 37 people | eyes open / closed | Training the comparison CNN: 58,636 (24 people) / 13,490 (5) / 12,772 (8) |

- **Splits:** by person; thresholds are chosen on the tuning set only.
- **Preprocessing:**
  - Live: 640 × 480 at 30 fps; at night, gray copied to 3 channels plus CLAHE contrast.
  - EAR is median-filtered and scaled to each driver's own open / closed calibration.
  - CEW: faces padded and resized to 400 × 400.
  - MRL: 32 × 32 gray, per-image normalisation, 9 augmentation types.
- CEW and MRL Eye numbers come from the version 2 Task 6 and Task 7 reports. The original files
  were lost in a PC reset.

### 1.4 Results

| Model | Accuracy | F1 | False alarms | Speed | Decision |
|---|---|---|---|---|---|
| **MediaPipe + EAR** | 94.6 % | **0.945** | 5.1 % | 5.1 ms | **Used** |
| YuNet + CNN (MRL Eye) | 93.5 % | 0.933 | 5.7 % | 11.8 ms | Dropped |
| Haar cascades | 80.7 % | 0.817 | 26.1 % | 9.5 ms | Dropped |

## Part 2: Phone, drink and eat model

### 2.1 Choices, in order

1. **Start with a ready COCO detector (YOLOv8n)** to test the rules before collecting data.
   - Bigger models were tested on the same 210-frame clip. None was worth its cost (table 2.2).
   - *Decision:* keep a small model and train it on in-car data.
2. **Try a ready State Farm classifier** (version 1 of this report). Dropped (table 2.2).
3. **Train YOLO26n on Open Images** photos converted to look like our camera.
   - *Why YOLO26n:* it is the newer version of the same small family, at the same size and speed.
     YOLO26 is also in the Hailo-8 model zoo, so the AI HAT can still run it.
   - *Result:* phone F1 0.825 on Open Images, but 0 % on a real webcam clip. Dropped.
4. **Ear and mouth crop classifiers on 3MDAD.** Phone F1 0.933 on 3MDAD, but 0.00 live. Dropped.
5. **Switch to SynDD as the main dataset.**
   - *Why:* its camera sits at the rear-view mirror, like ours.
   - 69 drivers, split 49 / 10 / 10; 18,318 auto-labelled frames.
6. **Merge five sources into one detector** (det_v2b, 53,889 training images).
   - *Result:* SynDD phone F1 0.717, vs 0.111 for the stock COCO model.
7. **det_v2d: gray-only training, 512 px, thresholds chosen on validation drivers.**
   - *Why:* to match the IR camera and cut false alarms.
   - *Result:* validation phone false alarms 36.1 → 5.2 per hour; test 1.7 → 0. Test calls
     80 % / 100 %, drinking 90 %.
   - **Release model.**
   - A head-down + wrist-low rule was added for texting: 36.6 % → 41.5 %.
   - Ten more ideas were tried; none beat det_v2d (table 2.2).
8. **Live test on the Pi showed det_v2d misses near-ear calls.** Replaced on the Pi (table 2.2).
9. **Action classifier + phone checks (v2).**
   - *How it works:* it names the driver's action from an upper-body crop. A call needs a phone
     seen at the ear; texting needs a phone seen in the lap.
   - *Why:* it does not need to see the phone itself, so a phone hidden by the hand still counts.
   - *Data change:* 3MDAD moved to training (35 drivers) for its near-ear examples.
   - *Result, same clips:* phone-use F1 **0.805 vs 0.543**; false alerts 24 vs 112. **Runs on the
     Pi.**
10. **Drinking: hand-at-mouth crop model (IR-4).**
    - *Why:* cup boxes came from a teacher model that missed many cups. Checking "is the hand at
      the mouth holding a cup?" is simpler. 22,612 crops.
    - *Result (IR test):* F1 **0.878 vs 0.735** for det_v2d. Same 18 / 20 caught, but 3 false
      alerts instead of 11. Meets the target.
11. **Eating: temporal model (GRU)** over about 2 s of hand-at-mouth crops.
    - *Result:* F1 0.634 (13 / 19, 10.15 false alarms per hour). Yawning is the main error.
      Does not meet the target; experimental.

### 2.2 Dropped and why

**Models and methods**

| Option | Why it was dropped | Numbers |
|---|---|---|
| Bigger COCO models (YOLOv8s, YOLO11n, YOLO11x) | Much slower for almost no gain; no COCO model knows snacks | Phone found in 38 / 210 frames (v8n, 23.6 ms), 44 (v8s, 87 ms), 28 (11n, 64.9 ms), 45 (11x, 263 ms) |
| State Farm classifier | Colour photos from the passenger side; our camera is IR at the mirror. Its ~99 % accuracy is the model card's claim, never measured on our data | — |
| YOLO26n on Open Images only | Photos do not transfer to a real cabin | Real clip: 0 % at the ear. SynDD: phone found in 27–35 % of frames, but also in 21.7 % of normal frames |
| Ear crop classifier (3MDAD) | 3MDAD's camera is low on the dashboard, 30–45° to the side, and sees the phone from the side. From the mirror, the hand hides it | F1 0.933 on 3MDAD, phone probability 0.00 live |
| Mouth crop classifier (3MDAD) | Called a cup at the lips "food" (48 % of drinking frames), and after a fix called a turned bare face "food" (32 %) | Drink F1 0.876 on 3MDAD, unusable live |
| Hands + pose + crop-classifier setup | One detector + three rules is simpler and faster | 12.2 fps vs 33 fps (laptop, same frame size) |
| det_v2b | More false alarms than det_v2d | Validation 36.1 vs 5.2 false alarms per hour |
| det_v2c (hard negatives, label fixing) | More false alarms | 13.7 vs 1.7 per hour on test |
| Tracking weak boxes | Also keeps false boxes alive | False alarms 5.2 → 27–38 per hour |
| Temporal model (det_v2d features) | Worse on phones; eating only at high cost | Eating needed 9–64 false alarms per hour |
| Second pass on a zoomed crop | Worse on test and slower | Right ear 70 % vs 80 %; 15.4 drink false alarms per hour; 26 → 18 fps |
| SynDD A2 pseudo-labels | Labels too noisy | Texting 47 % → 40 %; false alarms 5.2 → 6.9 per hour |
| Copy-pasted phones | Taught the model to fire near the ear | False alarms 5.2 → 41 per hour |
| SAM 2 recovered boxes | More false alarms | 5.2 → 20.6 per hour |
| Extra SynDD camera views | Other angles teach wrong shapes | 5.2 → 24.1 per hour |
| Fisheye-trained det_v2h | Better on simulated fisheye, worse on test | Test false alarms 0 → 6.9 per hour; kept as a backup for the real lens |
| det_v2d on the Pi (calls, texting) | The hand hides the phone at the near ear; a lower threshold costs false alarms; the steering wheel reads as a phone on real IR | Phone score 0.18 (near ear) vs 0.63 (far ear); near-ear rule 80 → 90 % at +3.4 false alarms per hour; DAD 69–79 false alarms per hour |
| Action v1 (no lap check) | Too many texting / drinking false alerts | 14.5 false alarms per hour on SynDD vs 0 for v2 |
| Larger action model ("s") | Not better, about 3× slower | 38.7 vs 14.5 false alarms per hour on SynDD |
| Extra "smoking" class | Did not remove smoking false alarms; worse elsewhere | Smoking false alarms 7 → 7; SynDD texting 18 → 11 of 41 |
| Lip-movement (talking) check | Never added call recall | — |
| det_v2d for drinking | More false alerts than IR-4, and too slow to run next to v2 on the Pi | 11 vs 3 false alerts; ~20 fps instead of ~30 |
| Strong camera simulation (drinking) | More false alarms | 1.09 → 3.26 per hour |
| All 5,310 phone negatives (drinking) | Lost recall | 14 → 12 of 15 |
| Eating by object boxes | Food is almost never visible from the mirror | Only 3 SynDD training frames with food |
| Eating by hand-to-mouth + chewing rule | Too weak | 0 / 19 |

**Datasets**

| Dataset | Why it was dropped or not used | Numbers |
|---|---|---|
| SynDD dashboard / side views | Other camera angles raised false alarms on the mirror view | 5.2 → 24.1 per hour |
| SynDD A2 | No labels; pseudo-labels too noisy | Texting 47 % → 40 % |
| State Farm, AUC | Passenger-side view | — |
| Drive&Act | Annotation files missing | 15 drivers of NIR video, unlabelled |
| DMD, 100-Driver | Requested, never received | — |
| YawDD | Never downloaded | — |

### 2.3 Data

| Dataset | IR / RGB | Size | Classes | Used for |
|---|---|---|---|---|
| SynDD A1, mirror view | gray (monochrome daylight, by pixel check) | 69 drivers, 18,318 labelled frames | calls, texting, drinking, eating, normal, look-alikes | Main training and test |
| Open Images V7 | RGB photos | 16,996 photos | phone, drink, food | Object appearance |
| Roboflow DMS_Project | IR + RGB | 10,198 images | phone, drinking, eating | Detector training |
| Roboflow ADMS_FINAL_3 | RGB | 2,698 images | phone, drinking | Detector training |
| EBDD | RGB → gray | 13 drivers, 2,093 frames | calls, texting, eating | Training and test |
| 3MDAD front | RGB → gray | 50 drivers, 650 clips | 16 actions | det_v2d test; v2 training (35 drivers) |
| DAD | **real IR** | 3 drivers, 66 min normal driving | calls, texting, drinking | Test only |

- **Splits** (by driver):

  | Dataset | Train | Validation | Test |
  |---|---|---|---|
  | SynDD | 49 drivers (13,385 frames) | 10 (2,534) | 10 (2,399) |
  | 3MDAD (v2) | 35 drivers | — | 15 drivers |
  | DAD | — | — | 3 drivers |

- **Detector set:** 53,889 train / 6,557 val / 4,780 test images.
  - Training boxes: phone 30,193, drink 47,605, food 24,786.
  - Includes 7,010 gray copies and 7,913 copies with a hand pasted over the phone.
  - SynDD training frames per action: phone at ear 4,424, texting 2,803, drinking 409, eating 3,
    normal 1,158, look-alikes 4,588.
- **Labels:**
  - Boxes come from a teacher model (YOLO26m at 1280 px; YOLO-World for food). A box is kept only
    if it matches the action label.
  - Roboflow boxes over 12 % of the image (8 % for drinks) are removed.
  - Box format: YOLO (class, x, y, w, h).
- **Preprocessing:**
  - Frames every 0.5 s in actions and 1.5 s in normal driving.
  - All images gray.
  - Detector 512 px; action crops 224 px; phone and cup crops 128 px with a contrast stretch.
- **Augmentation:**
  - Detector: mosaic, flip, zoom ±50 %, shift ±10 %, rotate ±5°, brightness ±40 %.
  - IR-4: light camera simulation.

### 2.4 Results

**Per image** (frame, box or crop)

| Model | Test data | Precision | Recall | F1 | Decision |
|---|---|---|---|---|---|
| Stock YOLO26n (COCO), phone | SynDD test | 0.71 | 0.06 | 0.111 | Baseline |
| YOLO26n, Open Images (512 px) | Open Images test | 0.82 | 0.83 | 0.825 | Dropped |
| Ear crop classifier, phone | 3MDAD drivers | 0.963 | 0.905 | 0.933 | Dropped |
| Mouth crop classifier, drink | 3MDAD drivers | 0.887 | 0.865 | 0.876 | Dropped |
| det_v2b, phone | SynDD test | 0.77 | 0.67 | 0.717 | Dropped |
| det_v2d, phone | SynDD validation | 0.818 | 0.628 | 0.711 | Release model |
| det_v2d INT8, phone | SynDD validation | 0.831 | 0.629 | 0.716 | Ready for the Pi |

Action classifier: per-frame accuracy 0.67 (SynDD) / 0.68 (3MDAD). Ear phone check: 0.984.
Lap phone check: 0.826 (AUC 0.84).

**Per alert** (the way the Pi works)

| Model | Behaviour | Test data | Caught (recall) | Precision | F1 | False alarms / h | Decision |
|---|---|---|---|---|---|---|---|
| det_v2d | phone use | SynDD + 3MDAD + DAD | 98/151 (0.649) | 0.467 | 0.543 | 0 / 14.2 / 79.2 | Replaced |
| **Action v2** | phone use | same clips | 118/151 (0.781) | 0.831 | **0.805** | 0 / 19.6 / 3.6 | **On the Pi** |
| Action v2 | calls | same clips | 72/74 (0.973) | 0.889 | 0.929 | — | On the Pi |
| Action v2 | texting | same clips | 46/77 (0.597) | 0.697 | 0.643 | — | On the Pi |
| det_v2d | drinking | IR test | 18/20 (0.900) | 0.621 | 0.735 | 0 / 8.67 | Replaced |
| **IR-4** | drinking | IR test | 18/20 (0.900) | 0.857 | **0.878** | 1.07 / 1.58 | **Ready, not on the Pi** |
| Eating GRU | eating | IR test | 13/19 (0.684) | 0.591 | 0.634 | 10.15 | Experimental |

- Precision = caught ÷ (caught + false alerts), from the false-alert lists in the result files.
- For phone use, any phone alert during a phone clip counts as correct.
- False alarms per hour are given per test set: SynDD / 3MDAD / DAD, or SynDD / DAD.

### 2.5 Current state

- **On the Pi:** the v2 action classifier for calls and texting, at about 30 fps.
- **No drinking or eating alerts on the Pi.**
  - In the running stream, drinking and eating come only from det_v2d, which is switched off
    (`--no-detect`).
  - Turning it on drops the stream to about 20 fps and brings back about 79 false phone alarms
    per hour on real IR video.
- **IR-4 (drinking) and the eating model:** the code is on main, but the Pi is not updated. It
  was unreachable and has no internet.
  - Even after updating, the alerts stay off until the stream is changed to use the new models.
  - The weights are not on GitHub.
- **Next:**
  1. Put IR-4 on the Pi and measure speed.
  2. Record our own drivers with the Pi camera.
  3. Calibrate the fisheye lens.
  4. Get true-IR eating data, or leave eating out.

## Part 3: Heart rate / HRV model

### 3.1 Choices, in order

1. **Wristband (MAX30102) → ESP32 → Pi, with every calculation on the Pi.**
   - *Why:* this is the Project 1 hardware. A sensor that only sends raw samples stays simple and
     cheap.
   - *Signal path:* 0.5–5 Hz filter, adaptive peak detector, beat intervals 300–2,000 ms, 60 s
     feature window.
   - *Result:* heart-rate error **0.51 bpm** against ECG (BIDMC record; p95 1.71 bpm; target 3).
     Error ≤ 0.05 bpm across a 26× change in packet size.
   - *On the Pi:* 1.31 % of one CPU core, about 109 MB of memory.
2. **Validate heart rate first, then train fatigue.**
   - *Why:* a fatigue score is only as good as the beats under it.
   - So the clinical BIDMC record was used before the WESAD data chosen in Project 1.
3. **Bad signal → no fatigue score, never a guess.**
   - *Result:* across 8 fault types (motion, clipping, contact loss, packet loss and others),
     0 fatigue scores were sent on a bad signal.
4. **Logistic regression** for the fatigue score.
   - *Why:* small enough for the Pi, and it gives calibrated probabilities.
   - Rule: switch to another model only if it improves leave-one-subject-out F1 by at least 0.05
     and AUROC by at least 0.03.
5. **Packet-loss fix.** A gap used to wipe the beat history.
   - Before the fix: heart-rate output fell from 70 % to 10 % of windows at 5 % packet loss.
   - After the fix: no drop up to 5 % loss (50 % → 50 %); about 31–33 % at 10 % loss and above.
6. **Garmin Forerunner 265 as the live wearable**, through a custom watch app that sends beat
   intervals to the Pi.
   - *Why:* the MAX30102 wristband is not built yet, and the watch is available now.
   - *Result:* 0 packets lost; last valid window HR 68.4 bpm, RMSSD 43.4 ms, SDNN 36.9 ms,
     pNN50 0.21 (normal resting values).
   - The wrist sensor sends beats in bursts: 156 of 321 packets carried no beats; window coverage
     0.3–0.9.
7. **Fatigue model trained on WESAD** (stress vs baseline).
   - *Result (LOSO, 15 subjects):* balanced accuracy 0.506, AUROC 0.545, average precision 0.503.
     Close to chance, so **experimental**.
8. **Role in fusion: confirm, not alarm.**
   - A fatigue score of 0.7 or more escalates an existing face or phone alert to the maximum
     level. On its own it only gives a short beep.
   - *Why:* the score is too weak to alarm alone (AUROC 0.545).

### 3.2 Dropped and why

| Option | Why it was dropped | Numbers |
|---|---|---|
| Random Forest / SVM (Project 1 plan) | Logistic regression is lighter and calibrated; the others were kept as candidates only if clearly better | Switch rule: +0.05 F1 and +0.03 AUROC (not tested yet) |
| Removing scipy to save memory | Pushed CPU over the 2 % limit | 1.97 % → 3.27 % of a core |
| Filling gaps in beat intervals (interpolation) | Would invent variability that was never measured | RMSSD / SDNN need ≥ 3 real intervals |
| Signal quality as a model feature | The model could learn motion as "fatigue"; quality only blocks the output instead | 0 leaks in 8 fault types |
| Garmin built-in heart-rate broadcast | Sends heart rate only, no beat intervals, so no HRV | Beat intervals in 0 of 217 messages |
| Windows laptop as the receiver | Windows never advertised the watch service | Receiver moved to the Pi |
| MAX30102 wristband (for now) | Not built yet; the Garmin watch works today | Same features feed the same model |
| WESAD model as a standalone alarm | Lab stress is not driving drowsiness; separation is near chance | AUROC 0.545 |

### 3.3 Data

| Dataset | Type | Size | Labels | Used for |
|---|---|---|---|---|
| BIDMC (record 01) | wrist PPG + ECG | 480 s, 60,001 samples | heart rate (from ECG) | Heart-rate accuracy |
| Synthetic signal | generated PPG with known beats | 50–120 bpm scenarios | true beats | Accuracy under packet sizes and faults |
| WESAD | wristband beat intervals | 15 subjects, 421 windows | baseline vs stress | Fatigue model (experimental) |
| Own Garmin session | watch beat intervals | 5 min, 321 packets | — | Live pipeline check |
| PPG-DaLiA, BUT PPG | PPG under motion | — | heart rate | Planned (motion test) |

- **Split:** WESAD leave-one-subject-out: 14 subjects train, 1 tests, rotated 15 times.
- **Preprocessing:**
  - PPG at 100 Hz, filtered 0.5–5 Hz.
  - Beat intervals outside 300–2,000 ms are rejected.
  - Garmin and WESAD beats go through the same HRV code.
- **Features** (per 60 s window): mean HR, HR slope, median interval, log RMSSD, SDNN, pNN50,
  CVNN.
- **Quality gate:** good / degraded / bad. A bad window gives no fatigue score.

### 3.4 Results

| Part | Test data | Result | Decision |
|---|---|---|---|
| Heart-rate signal path | BIDMC vs ECG | Error 0.51 bpm (p95 1.71); 1.31 % CPU, 109 MB | **Used** |
| Heart-rate signal path | synthetic, 26× packet sizes | Error ≤ 0.05 bpm | Used |
| Fault handling | 8 fault types | 0 fatigue scores on a bad signal | Used |
| Garmin watch app → Pi | own 5-min session | 0 packets lost; HR 68.4 bpm, RMSSD 43.4 ms | **Used (live wearable)** |
| WESAD fatigue model | 15 subjects, LOSO | Balanced accuracy 0.506, AUROC 0.545, AP 0.503 | Experimental |

### 3.5 Current state

- The heart-rate / HRV path works. The Garmin receiver can run on the Pi as a separate service, with
  live HRV every 5 s.
- The WESAD fatigue model is experimental and sits on an unmerged branch
  (`physio/wesad-fatigue-train`).
- **Next:**
  1. Log Garmin data together with the face model's drowsy / normal state.
  2. Retrain the fatigue model on it.
  3. Tune the 0.7 confirm threshold.
  4. Measure CPU with all three models running together.

## Sources

| Part | Files |
|---|---|
| Face | Task 6 v2 (Figures 2–3, Tables 2–3) and Task 7 v2 (Table 13, Figures 1–2); `models/face/docs/EVIDENCE.md`; `Subsystems/Face Subsystem.md`; session record of the face-model design |
| Phone, drink, eat | `models/distraction/docs/` (EVIDENCE, DATA, MORNING_REPORT, SYNDD_RETRAIN, DETECTOR_V2, OVERNIGHT_REPORT); `action_v1/` (REPORT, REPORT_v2, PROGRESS, DECISIONS, ir_report, ir_log, HELD_OBJECT, dataset_inventory); session records of the model comparison and the live Pi test |
| Heart rate / HRV | `models/physiology/docs/EVIDENCE.md`, `docs/garmin/STEP1_2_RESULTS.md`; `Subsystems/Physiology Subsystem.md`; branches `physio/wesad-fatigue-train` (WESAD.md, fatigue_wesad_v1.json) and `docs/physio-fusion-approach` |
| Data counts | data-build logs; Task 6 v2 Figures 5–6 |

Some F1 and precision values are calculated from the precision, recall and false-alert counts in
these files. The full history is in `timeline.md`.
