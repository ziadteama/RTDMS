# Task 6: Dataset Preparation and Preprocessing (version 3)

**Project:** Real-Time Driver Monitoring System (RTDMS)
**Scope:** face monitoring, phone / drink / food (distraction) detection, and heart rate / HRV
**Prepared by:** Youssef Medhat, Omar Deyaa (face and distraction models), Ziad Teama (heart rate / HRV)
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
- **Heart rate / HRV:**
  - Heart rate is accurate: 0.51 bpm error against ECG.
  - The live wearable is a Garmin watch streaming RR intervals to the Pi.
  - The fatigue model is experimental: AUROC 0.545, close to chance.
- **The Pi currently gives no drinking or eating alerts** (section 6).

Target for vision: at least 85 % caught (F1 ≥ 0.85) and at most 5 false alarms per hour.
Target for heart rate: error at most 3 bpm.

## 2. Sequence of choices

### Face model

1. **MediaPipe face mesh + EAR / PERCLOS rules.**
   - *Why:* the model is pre-trained and small (0.6 M parameters), so it runs on the CPU and
     leaves the AI HAT free.
   - *Result on CEW (1,696 test photos):* F1 0.945, accuracy 94.6 %, 5.1 % false alarms,
     5.1 ms per frame.
   - *Result on the Pi:* 30 fps (the camera's limit), 13.5 ms per frame, 133 MB of memory.
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
   - *Result:* phone F1 0.825 on Open Images (stock COCO model: 0.809), but **0 %** of
     phone-at-ear frames found on a real webcam clip.
   - *Lesson:* photos do not transfer; in-car video is needed.
4. **Ear and mouth crop classifiers on 3MDAD.**
   - *Result:* phone F1 0.933 and drink F1 0.876 on held-out 3MDAD drivers, but 0.00 live.
   - *Dropped:* 3MDAD's camera is low on the dashboard and sees the phone from the side. From the
     mirror, the hand hides it.
5. **SynDD becomes the main dataset.**
   - *Why:* its camera sits at the rear-view mirror, like ours.
   - *Data:* 69 drivers, split by driver 49 / 10 / 10; 18,318 auto-labelled frames.
6. **Detector v2: five sources merged** to 53,889 training images.
   - *Result (det_v2b), SynDD test:* phone F1 0.717 (stock COCO: 0.111); phone at the ear found
     in 71.5 % / 91.6 % of frames.
7. **det_v2d: gray-only images, 512 px, thresholds chosen on validation drivers.**
   - *Why:* to match the IR camera and cut false alarms.
   - *Result:* validation phone false alarms fell from 36.1 to 5.2 per hour. Test drivers: calls
     80 % / 100 %, drinking 90 %, 0 false alarms per hour. **Became the release model.**
   - Eight other ideas did not beat it. Extra SynDD camera views, for example, raised false
     alarms to 24.1 per hour.
   - A head-down + wrist-low rule raised texting from 36.6 % to 41.5 %.
   - A 5-fold check across 59 drivers gave mean calls 89 % / 97 %, drinking 66 %, and 9.0 false
     alarms per hour. Results move 10–25 points between driver groups.
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

### Heart rate / HRV (physiology)

1. **MAX30102 wristband → ESP32 → Pi; every calculation on the Pi.**
   - *Why:* this is the Project 1 hardware choice. A sensor that only sends raw samples is simple
     and cheap.
   - *Signal path:* 0.5–5 Hz filter, adaptive peak detector, beat intervals 300–2,000 ms, 60 s
     feature window.
   - *Result (BIDMC clinical record, against ECG):* heart-rate error 0.51 bpm (p95 1.71 bpm).
     The target is 3 bpm.
   - *Result (synthetic test signal):* error ≤ 0.05 bpm across a 26× change in packet size.
   - *Result on the Pi:* 1.31 % of one CPU core, 108.5–109.7 MB of memory, no throttling.
   - *Safety:* across 8 fault types (motion, clipping, contact loss, packet loss and others),
     no fatigue score was ever sent while the signal was bad.
2. **Logistic regression instead of the planned Random Forest / SVM.**
   - *Why:* it fits the Pi budget and gives calibrated probabilities. It is kept unless another
     model improves leave-one-subject-out F1 by at least 0.05 and AUROC by at least 0.03.
3. **Removing scipy to save memory: reverted.**
   - *Result:* CPU rose from 1.97 % to 3.27 % of a core, over the 2 % limit.
4. **Packet-loss fix.** Any gap used to wipe the beat history.
   - Before the fix, heart-rate output fell from 70 % to 10 % of windows at 5 % packet loss.
   - After the fix, it does not drop up to 5 % loss (50 % → 50 %).
   - At 10 % loss and above it is still about 31–33 %.
5. **Switch the live wearable to a Garmin Forerunner 265.**
   - *Why:* the MAX30102 wristband is not built yet, and the watch is a wearable already on hand.
   - The watch's built-in heart-rate broadcast has **no RR intervals** (0 of 217 messages), so it
     cannot give HRV. *Dropped.*
   - A custom watch app does give RR intervals (for example 817 ms = 73 bpm). It streams them to
     the Pi with 0 packets lost.
   - *Result (5-min resting session):*
     - 156 of 321 packets carried no beats, because the wrist sensor reports in bursts.
     - Window coverage was 0.3–0.9.
     - Last valid window: HR 68.4 bpm, RMSSD 43.4 ms, SDNN 36.9 ms, pNN50 0.21 (normal
       resting values).
6. **Fatigue model trained on WESAD.**
   - *Data:* 15 subjects, 421 windows, labels baseline vs stress, split by subject (LOSO).
   - *Result:* balanced accuracy 0.506, AUROC 0.545, average precision 0.503. This is close to
     chance.
   - *Why it stays experimental:* lab stress is not driving drowsiness, and the E4 wristband's
     beats are not the Garmin's.
7. **Role in fusion: confirm, not alarm.**
   - A fatigue score of at least 0.7 escalates an existing face or phone alert to the maximum
     level.
   - On its own, it only gives a short beep.
   - *Next:* retrain on Garmin data logged together with the face model's drowsy / normal state.

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
| BIDMC (record 01) | PPG + ECG | 480 s, 60,001 samples | heart rate | Used | Heart-rate accuracy vs ECG |
| WESAD | wrist BVP / beats | 15 subjects, 421 windows | baseline vs stress | Used (experimental) | Chosen in Project 1; stress labels as a stand-in for fatigue |
| Own Garmin session | RR intervals | 5 min, 321 packets | — | Used | Live pipeline check |
| PPG-DaLiA, BUT PPG | PPG | — | heart rate under motion | Not yet used | Planned for motion testing |
| State Farm | RGB | 22,424 images | 10 classes | Dropped | Passenger-side view |
| AUC | RGB | about 44 drivers | 10 classes | Not used | Passenger-side view |
| Drive&Act | NIR | 15 drivers | many | Not used | Labels missing |
| DMD, 100-Driver | IR + RGB | — | many | Not used | Never received |

CEW, MRL Eye and the State Farm, DMS_Project and ADMS_FINAL_3 counts come from the version 2
Task 6 and Task 7 reports. The original CEW and MRL Eye files were lost in a PC reset.

## 4. Data preparation

- **Splits:** always by driver, person or subject, so no test person appears in training.

  | Dataset | Train | Validation | Test |
  |---|---|---|---|
  | SynDD | 49 drivers (13,385 frames) | 10 (2,534) | 10 (2,399) |
  | 3MDAD (v2) | 35 drivers | — | 15 drivers |
  | DAD | — | — | 3 drivers |
  | CEW | 727 photos for tuning | — | 1,696 photos (834 closed, 862 open) |
  | MRL Eye | 58,636 images, 24 people | 13,490, 5 people | 12,772, 8 people |
  | WESAD | 14 subjects | — | 1 subject, rotated 15 times (LOSO) |

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
- **Preprocessing (vision):**
  - Frames every 0.5 s in actions and 1.5 s in normal driving.
  - All images gray.
  - Detector input 512 px; action crops 224 px; phone and cup crops 128 px with a contrast
    stretch.
  - Face images: CEW faces padded and resized to 400 × 400; MRL eyes 32 × 32 gray.
- **Preprocessing (heart rate):**
  - PPG at 100 Hz, filtered 0.5–5 Hz.
  - Beat intervals outside 300–2,000 ms are rejected and never interpolated.
  - Features per 60 s window: mean HR, HR slope, median interval, log RMSSD, SDNN, pNN50, CVNN.
  - Bad-quality windows give no fatigue score.
  - WESAD: wristband beat intervals → the same features as the Garmin path.
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

**Frame, box and crop level** (per image)

| Model | Test data | Accuracy | Precision | Recall | F1 | Decision |
|---|---|---|---|---|---|---|
| Stock YOLO26n (COCO), phone | SynDD test | — | 0.71 | 0.06 | 0.111 | Baseline |
| YOLO26n, Open Images (416 px) | Open Images test | — | 0.81 | 0.82 | 0.815 | Dropped |
| YOLO26n, Open Images (512 px) | Open Images test | — | 0.82 | 0.83 | 0.825 | Dropped: 0 % on a real clip |
| Ear crop classifier, phone | 3MDAD drivers | — | 0.963 | 0.905 | 0.933 | Dropped: 0.00 live |
| Mouth crop classifier, drink | 3MDAD drivers | — | 0.887 | 0.865 | 0.876 | Dropped |
| Ear crop classifier, phone | SynDD drivers | — | 0.983 | 0.867 | 0.921 | Off by default |
| Mouth crop classifier, drink | SynDD drivers | — | 1.000 | 0.771 | 0.871 | Off by default |
| det_v2b, phone | SynDD test | — | 0.77 | 0.67 | 0.717 | Replaced |
| det_v2b, phone | EBDD test | — | 0.87 | 0.63 | 0.731 | Replaced |
| det_v2b, drink | SynDD test | — | 0.83 | 0.53 | 0.647 | Replaced |
| det_v2d, phone (512 px, gray) | SynDD validation | — | 0.818 | 0.628 | 0.711 | Release model |
| det_v2d INT8, phone | SynDD validation | — | 0.831 | 0.629 | 0.716 | Ready for the Pi |
| Action classifier (n) | SynDD / 3MDAD test | 0.67 / 0.68 | — | calls 0.94 / 0.84 | — | Used in v2 |
| Action classifier (s) | SynDD validation | 0.664 | — | — | — | Rejected: 3× slower |
| Action + smoking class | SynDD validation | 0.657 | — | — | — | Rejected |
| Ear phone check | SynDD validation | 0.984 (INT8 0.986) | — | — | — | Used in v2 |
| Lap phone check | SynDD validation | 0.826 (INT8 0.823) | — | — | — | Used in v2 (AUC 0.84) |

**Alert level** (per event, the way the Pi works)

| Model | Behaviour | Test data | Caught (recall) | Precision | F1 | False alarms / h | Decision |
|---|---|---|---|---|---|---|---|
| det_v2d | calls R / L, drinking | SynDD test | 80 % / 100 %, 90 % | — | — | 0 | Release |
| det_v2d recipe, 5-fold | calls R / L, drinking | 59 drivers | 89 % / 97 %, 66 % | — | — | 9.0 (2.8–22.4) | Spread check |
| det_v2d | calls | 3MDAD, 50 drivers | 80–92 % | — | — | 8 % of normal clips | Unseen test |
| det_v2d | calls, drinking | DAD (real IR) | 4/5, 2/2 | — | — | 69 | Unseen test |
| det_v2d | phone use | SynDD + 3MDAD + DAD | 98/151 (0.649) | 0.467 | 0.543 | 0 / 14.2 / 79.2 | Replaced by v2 |
| Action v1 | calls | same clips | 72/74 (0.973) | — | — | 14.5 / 71.2 / 0 | Replaced by v2 |
| **Action v2** | phone use | same clips | 118/151 (0.781) | 0.831 | **0.805** | 0 / 19.6 / 3.6 | **Runs on Pi** |
| Action v2 | calls only | same clips | 72/74 (0.973) | 0.889 | 0.929 | — | Runs on Pi |
| Action v2 | texting only | same clips | 46/77 (0.597) | 0.697 | 0.643 | — | Runs on Pi |
| det_v2d | drinking | IR test | 18/20 (0.900) | 0.621 | 0.735 | 0 / 8.67 | Replaced |
| **IR-4** | drinking | IR test | 18/20 (0.900) | 0.857 | **0.878** | 1.07 / 1.58 | **Best; not on Pi** |
| Hand-to-mouth + chewing rule | eating | SynDD test | 0/19 | — | — | — | Dropped |
| Eating GRU | eating | IR test | 13/19 (0.684) | 0.591 | 0.634 | 10.15 | Experimental |

How the alert-level numbers are counted:
- **Precision** = caught events ÷ (caught events + false alerts), using the false alerts listed
  in `REPORT_v2.md` and `ir_report.md`.
- **Phone use:** any phone alert during a phone clip counts as correct.
- **False alarms per hour** are listed per test set: SynDD / 3MDAD / DAD, or SynDD / DAD.
- "—" means the source gives no false-alert list for that row.

**Heart rate / HRV**

| Model | Test data | Result | Decision |
|---|---|---|---|
| HR signal path (MAX30102 design) | BIDMC record 01 vs ECG | HR error 0.51 bpm (p95 1.71); 1.31 % CPU, 109 MB | **Used** |
| HR signal path | synthetic signal, 26× packet sizes | error ≤ 0.05 bpm | Used |
| Same path without scipy | Pi | CPU 3.27 % (limit 2 %) | Reverted |
| Garmin built-in HR broadcast | own session | RR in 0 of 217 messages | Dropped: no HRV |
| Garmin watch app → Pi | own 5-min session | 0 packets lost; HR 68.4 bpm, RMSSD 43.4 ms | **Used (live wearable)** |
| WESAD logistic fatigue model | WESAD, 15 subjects, LOSO | balanced accuracy 0.506, AUROC 0.545, AP 0.503 | Experimental |

## 6. Current state

- **On the Pi:**
  - Face mesh + PERCLOS.
  - The v2 action classifier for calls and texting, at about 30 fps.
  - Also available: the Garmin RR receiver, with live HRV every 5 s (a separate service).
- **No drinking or eating alerts on the Pi.**
  - In the running stream, these come only from the det_v2d detector, which is switched off
    (`--no-detect`).
  - Turning it back on drops the stream to about 20 fps and brings back about 79 false phone
    alarms per hour on real IR.
- **New drinking (IR-4) and eating models:** the code is on main, but the Pi is not updated. It
  was unreachable and has no internet.
  - Even after updating, the alerts stay off until the stream is changed to use the new models.
  - The weights are not on GitHub.
- **Heart rate:**
  - The HR / HRV path works.
  - The WESAD fatigue model is experimental (AUROC 0.545) and sits on an unmerged branch
    (`physio/wesad-fatigue-train`).
  - The MAX30102 wristband is not built yet.
  - Not measured yet: concurrent CPU use with the vision models.
- **Next:**
  1. Put IR-4 on the Pi and measure speed.
  2. Record our own drivers with the Pi camera.
  3. Calibrate the fisheye lens.
  4. Get true-IR eating data, or leave eating out.
  5. Log Garmin data together with the face model's state, retrain the fatigue model on it, and
     tune the 0.7 confirm threshold.

## Sources

| Section | Files |
|---|---|
| Face, CEW, MRL Eye | Task 6 v2 (Figures 2–3, Tables 2–3) and Task 7 v2 (Table 13, Figures 1–2); `models/face/docs/EVIDENCE.md` |
| Phone steps 1–2 | session record (model comparison); `models/phone/docs/EVIDENCE.md`; Task 7 v2 Table 3 |
| Phone steps 3–8 | `models/distraction/docs/` EVIDENCE, DATA, MORNING_REPORT, SYNDD_RETRAIN, DETECTOR_V2, OVERNIGHT_REPORT |
| Phone step 9 | session record of the live Pi test |
| Phone step 10, phone tables | `action_v1/REPORT.md`, `REPORT_v2.md` (results and false-alarm list), `PROGRESS.md`, `DECISIONS.md` |
| Steps 11–12, drinking and eating | `action_v1/ir_report.md`, `ir_log.md`, `HELD_OBJECT.md`, `dataset_inventory.md` |
| Heart rate / HRV | `models/physiology/docs/EVIDENCE.md`, `docs/garmin/STEP1_2_RESULTS.md`, `Subsystems/Physiology Subsystem.md`; branch `physio/wesad-fatigue-train` (`docs/WESAD.md`, `models/fatigue_wesad_v1.json`); branch `docs/physio-fusion-approach` |
| Data counts | data-build logs; Task 6 v2 Figures 5–6 |
| Current state | `pi/start_stream.sh`, `action_v1/.gitignore`, `action_v1/ir_report.md` §5 |

F1 values for the frame-level models and all alert-level precision and F1 values are calculated
from the precision, recall and event counts in these files. The full history is in `timeline.md`.
