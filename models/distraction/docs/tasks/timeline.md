# RTDMS face + distraction work: timeline, first day to now

Scope: the face model and the phone / drink / food (distraction) models, plus their datasets
and the camera/Pi setup. Physiology (HR/HRV, Garmin) is listed only when it touched the shared
Pi or repo.

Every number below has its source next to it. Dates: transcript times are UTC; git dates are
the committer's local time as git recorded it.

## How the history was rebuilt

| Source | What I could read |
|---|---|
| Current Task 6 report (PDF, this folder) | All of it |
| Git history (128 commits, all branches after `git fetch --unshallow`) | All commit messages; key docs and code read in full |
| Repo docs and configs (`models/distraction`, `models/phone`, `models/face`, `Subsystems/`) | All docs named in `report_vs_project.md` |
| `./chat_exports/` | **Folder does not exist.** NOT FOUND |
| Local `~/.claude/projects/*.jsonl` | Only this session (this cloud machine is new). Old local transcripts are gone |
| Remote Claude Code session transcripts (saved on your account) | See the coverage table below |

**Transcript coverage** (times UTC):

| Session (title) | Dates | Read |
|---|---|---|
| Real-Time DMS face monitoring research survey | 2026-08-27 23:33 → 08-28 15:36 | All |
| Lightweight distraction detection model research | 2026-08-28 15:09 → 17:50 | All |
| Backend architecture study (3 sessions) | 2026-08-31 → 09-15 | **Not read** (titles say a different topic) |
| Raspberry Pi 5 camera setup | 2026-10-09 20:12 → 23:03 | All |
| RTDMS distraction module on Raspberry Pi | 2026-10-10 16:07 → 10-11 20:25 | **Partly**: 10-11 00:16 → 20:25 read; **10-10 16:07 → 10-11 00:16 not read** (too long; that day is covered by git commits and EVIDENCE.md / DATA.md written in it) |
| RTDMS graduation project rebuild (A, B) | 2026-10-16 02:23 → 17:30 | All |
| RTDMS graduation project rebuild (C) | 2026-10-16 18:27 → 11-07 14:24 | **Mostly**: 10-18 03:44 → 11-07 14:24 read (10-19 → 10-25 20:30 had almost no activity: one page jumps from 10-18 21:31 to 10-25 20:32). **10-16 18:27 → 10-18 03:44 not read** (the overnight experiment runs; OVERNIGHT_REPORT.md and DETECTOR_V2.md were written in that window) |
| RTDMS graduation project rebuild (D) | 2026-11-07 14:30 → 11-09 08:34 | 11-07 15:05 → end read (mostly Garmin) |
| RTDMS project reports by task (run on another team member's PC) | 2026-11-08 | All |
| Face model texting/eating/drinking enhancement | 2026-11-08 20:56 → 11-15 01:06 | All |

**PC resets.** The 2026-10-16 rebuild session starts with: "My PC was reset and my local Claude
Code project was lost" (session 2026-10-16 02:23). You confirmed this was the **only** PC reset.
Everything that only lived on the PC before it is marked "(reset period)" below. The remote
transcripts above survived it.

---

## Stage 0. Project 1 plan (report dated May 2026)

- **What:** the Project 1 report set the plan: Raspberry Pi 5 + AI HAT+ 26 TOPS, Pi IR camera
  5MP 160°, MediaPipe Face Mesh for EAR/PERCLOS/gaze/head pose, YOLOv5 for phone detection.
  Source: `CLAUDE.md` ("Selected hardware", "Software stack"), `Report/`.
- **Datasets chosen then:** UTA-RLDD, AUC Distracted Driver, MRL Eye, DG-Unicamp, WESAD; reviewed
  but not selected: CEW, Drive&Act, NDS. Source: `CLAUDE.md` ("Datasets").
- **Accuracy target:** ≥ 85–90 % for each vision task; < 500 ms end to end. Source: `CLAUDE.md`.

## Stage 1. 2026-08-27/28: first face model (dms-face)

- **What:** built a face package on MediaPipe FaceLandmarker (Tasks API), with EAR, blinks,
  PERCLOS, head pose and gaze computed by geometry. Published as `youssefmedhat4/dms-face`
  (session 2026-08-28 15:36), later adopted into the monorepo at commit `65e3afd`
  (`Subsystems/Face Subsystem.md`, adopted 2026-09-20).
- **Why this design (reasons given at the time, session 2026-08-27 23:59):**
  - The MediaPipe `solutions` API is gone in MediaPipe ≥ 1.0, so the Tasks API had to be used.
  - The face landmark model is small (Hailo zoo: 0.6 M params / 0.07 GOPS), so it runs on the
    CPU and the AI HAT is left for phone detection.
  - The 2–3 s eye-closure alert from Project 1 is "too late", so alert at 1.0–1.5 s instead.
    The face code later used 1.5 s (`Subsystems/Face Subsystem.md`).
- **Numbers:**
  - 31 unit tests at first, then 38 (session 2026-08-28 01:34 and 02:47).
  - Webcam at 30.0 fps (301 frames in 10 s).
  - One measured face: calibration SNR 69.7 (session 2026-08-28 02:47; `models/face/docs/EVIDENCE.md`).
- **Datasets:** none used for training (pre-trained Google model). MRL Eye was named only as a
  possible future eye-state CNN for drivers whose EAR signal is poor (session 2026-08-28 02:47).
  CEW and the MRL-trained CNN are in stage 1b.
- **Sources disagree on iris landmarks.** Session 2026-08-28 01:34 says "478 landmarks with iris
  confirmed". Session 2026-08-28 16:56 says iris landmarks were absent in 1270 of 1270 frames
  ("bundled face_landmarker.task emits 468 points"). Later Pi notes say 478 points
  (`models/face/docs/EVIDENCE.md`).

## Stage 1b. Date not recorded (before 2026-10-18): CEW test and MRL Eye CNN (reset period)

- **What:** you did this work outside Claude Code. The original files were lost in the PC reset
  (your answer, 2026-11-16). No code, log or transcript exists for it.
- **From the old report, not verified** (Task 6 v2 §2, which says this part was "unchanged since
  version 1"):
  - CEW: 2,423 face photos (1,192 closed, 1,231 open), colour 100 × 100. Split 30 % tuning (thresholds
    only) / 70 % test. Faces padded with a 50 % border, then 400 × 400.
  - MRL Eye: 84,898 infrared eye images from 37 people, used to train an eye-state CNN as a
    comparison. Split by person (8 people never seen). 32 × 32 gray, per-image normalisation,
    9 augmentation types.
  - The old report gives **no accuracy numbers** for either.
- MRL Eye is still on D: (383 MB), listed as not used (INVENTORY 2026-11-14).
- **Not counted in the final results.**

## Stage 2. 2026-08-28: first distraction research and prototype (dms-distract)

- **Research result** (session 2026-08-28 15:20):
  - **Model:** one 4-class YOLOv8n detector (phone, bottle, cup, food) on the Hailo-8, fed a
    driver crop from the face model, with rules on top.
  - **Why YOLOv8n and not YOLO11n / YOLO26n:** it survives INT8 better on Hailo. Hailo zoo:
    37.0 → 36.4 mAP for yolov8n vs −1.5 for yolov11n.
- **Datasets proposed then:** Drive&Act NIR, DMD IR, State Farm, SynDD2 (named as "the only
  eating data"), AUC "if licensed", plus 2.5–4k of our own rig images (session 2026-08-28 15:20).
  Finding at the time: "No public driver dataset ships bounding boxes", so plan auto-label + hand
  correction.
- **Prototype:** stock COCO YOLOv8n with COCO classes collapsed to phone / bottle / cup / food, no
  training. Tested live on the laptop webcam:
  - 4 actions caught, 0 false positives on the scripted clip after fixes (session 2026-08-28 17:01).
  - 46 tests (session 2026-08-28 17:50).
- **Model comparison on our own 210-frame webcam clip** (session 2026-08-28 16:44):

  | Model | ms / image | Phone frames | Phone conf p50 | Food conf p50 |
  |---|---|---|---|---|
  | yolov8n | 23.6 | 38 / 210 | 0.21 | 0.08 |
  | yolov8s | 87.0 | 44 / 210 | 0.28 | 0.12 |
  | yolo11n | 64.9 | 28 / 210 | 0.44 | 0.08 |
  | yolo11x | 263.0 | 45 / 210 | 0.66 | 0.26 |

  **Decision:** no bigger YOLO, fine-tune the nano model on cabin data. Reason: "A model 25×
  more expensive finds the phone in 7 more frames out of 210" and COCO has no class for most
  snacks.
- **Hardware:** laptop webcam only (~9.7 fps in that light, session 2026-08-28 16:04).

## Stage 3. 2026-09-20 → 09-25: face adopted; version 1 phone model (State Farm)

- **2026-09-20:** face package adopted into the monorepo (`CLAUDE.md`; commit `8026fc2`).
- **2026-09-25, `models/phone` (commit `2515a90`, author Ziad Teama):** this is the "version 1"
  of the Task 6 report.
  - **Model:** ready YOLOv8n-cls weights (Hugging Face Safe-Drive-TN, State Farm 10 classes)
    exported to ONNX, collapsed to safe / phone / eating, 224 px, 5 Hz.
  - **Why:** "Ready weights, no local train"; AUC deferred, "no signed license gate" for State Farm.
  - **Numbers:**
    - The Hugging Face card claims ~99 % top-1, "treat as optimistic / possible leakage".
    - Phone metrics "Not yet measured on hold-out".
    - Host ONNX ~11 ms mean over 20 runs.
    - Source: `models/phone/docs/EVIDENCE.md`.
  - **Known gap at the time:** "State Farm is RGB cabin; IR domain gap remains"
    (`models/phone/docs/EVIDENCE.md`).
- **(reset period)** The first Task 6 report (version 1) described this model. It existed in
  Downloads by 2026-10-18 (stage 9b); when it was written is NOT FOUND.

## Stage 4. 2026-10-09: camera on the Pi, face live on the Pi

- **Camera attached:** "OV5647 clone ... RGB, no IR, a stand-in for development until the BOM's
  IR 160° module arrives" (450 EGP). Face uses 640×480 @ 30 fps (`Subsystems/Raspberry Pi 5 Target.md`, Camera).
- **Face on the Pi:**
  - Runs the same `.tflite` networks on **LiteRT** instead of MediaPipe or ONNX. Reason: MediaPipe
    won't run on the Pi's Python 3.13 ("Blocker 1", session 2026-10-09 21:50).
  - 30.0 FPS (camera-bound), mesh 13.5 ms, pipeline 14.1 ms of 33 ms, 73 % of one core, 133 MB,
    ~50 °C, no throttling (session 2026-10-09 21:39; `models/face/docs/EVIDENCE.md`).
- **COCO YOLOv8n phone/drink/food prototype on the Pi:** YOLO at 5 Hz taking 102 ms, ~21 % CPU,
  184 MB (session 2026-10-09 22:30).

## Stage 5. 2026-10-10: new distraction module; first trained detector (Open Images)

- **What:** new package `models/distraction` with a **YOLO26n** detector (NCNN/ONNX), fisheye
  rectification, face mesh on a face crop, rules, event log (commits `e35c3da` … `f387f94`).
  - The reason for switching from YOLOv8n (stage 2) to YOLO26n is NOT FOUND in the parts I read.
  - The later action model notes call yolo26 "the newer generation of the same family, same
    size/speed class" (`action_v1/DECISIONS.md` D10).
- **Data decision:** "**no self-recorded training data**. The detector is trained on public
  datasets made to look like our camera. Our own clips are TEST data only" (`docs/DATA.md`, dated 2026-10-10).
- **Teacher choice for auto-labels** (40-image check vs Open Images ground truth, `docs/DATA.md`):
  - YOLO-World v2-L at conf 0.10 for food (recall 0.24, 1 unmatched box).
  - MediaPipe Hands for hands (recall 0.24, 5 unmatched).
  - YOLOE-26l rejected (hand recall 0.04–0.25; "overflowed 8 GB").
- **Dataset: Open Images V7**, converted to our camera (gray, head-and-shoulders crop, fisheye
  geometry, real-hand occluders, IR look). Up to 4000 images per class for train, 400 for val/test.
  Classes: phone, drink, food, hand (`docs/DATA.md`, `configs/data.yaml`).

  | Split | Images | Phone | Drink | Food | Hand boxes |
  |---|---|---|---|---|---|
  | train | 13,623 | 5,762 | 27,406 | 14,449 | 17,946 |
  | val | 815 | 135 | 969 | 669 | 897 |
  | test | 937 | 343 | 1,596 | 1,243 | 880 |

  Source: `docs/EVIDENCE.md` ("Public-data fine-tune v1").
- **Models v1_416 / v1_512** (yolo26n from COCO, 60 epochs). Open Images test, P / R / AP50
  (`docs/EVIDENCE.md`):

  | Class | Stock yolo26n @416 | v1_416 | v1_512 |
  |---|---|---|---|
  | phone | 0.88 / 0.48 / 0.65 | 0.81 / 0.82 / 0.86 | 0.82 / 0.83 / 0.87 |
  | drink | 0.75 / 0.16 / 0.28 | 0.64 / 0.35 / 0.42 | 0.66 / 0.36 / 0.45 |
  | food | 0.73 / 0.06 / 0.21 | 0.59 / 0.30 / 0.36 | 0.57 / 0.29 / 0.36 |

- **Result on a real clip (S01, developer webcam):** phone at the ear 0.00 for every model.
  - Conclusion at the time: "Large gains on converted Open Images do not transfer to a real camera
    clip ... in-cabin video data (SynDD rear view, DMD, 100-Driver) is the critical path"
    (`docs/EVIDENCE.md`).
- **Speed (laptop, not Pi):** 19.9 FPS end to end, detector 30.4 ms of 46.5 ms (`docs/EVIDENCE.md`).
- **Pi:** "unreachable" that day, so no Pi numbers (`docs/EVIDENCE.md`).

## Stage 6. 2026-10-11: laptop colour target; ear / mouth crop classifiers; camera placement

- **Target changed to the laptop webcam, in colour**, IR and fisheye parked (`docs/LAPTOP_TESTING.md`,
  `docs/DATA.md`: "2026-10-11: current target is the laptop webcam in colour"). Reason given:
  live testing on the laptop. The IR Pi camera was "parked".
- **New models:** YOLO26n-cls crop classifiers. Ear crop: phone / hand_no_phone / none. Mouth
  crop: drink / food / none.
  - **Data:** 3MDAD front view (Day-RGB2, 50 drivers, RGB) + Open Images, split by driver 70/15/15.
  - **Labels:** drink labels from CLIP ViT-L/14 zero-shot (≥ 0.97) because "yolo26m (COCO),
    YOLO-World and MediaPipe hands missed most cups at the lips" (`docs/DATA.md`).
  - **Results on test drivers** (`docs/MORNING_REPORT.md`):
    - Ear 160 px: phone P 0.963 / R 0.905; hand_no_phone 0.568 / 0.761; none 0.941 / 0.943.
    - Mouth 96 px (CLIP-labelled): drink 0.887 / 0.865; food 0.933 / 0.933 (only 15 crops);
      none 0.930 / 0.942.
  - **Crop size chosen on val:** ear 160 (val F1 0.910), mouth 96 (val F1 0.947).
  - **Laptop FPS:** hands 16.5, hands+pose 15.8, hands+pose+clf 12.2.
- **Dropped the same day:**
  - **Ear classifier off.** Reason: 3MDAD's camera "sits low on the dashboard ... sees the face
    at 30-45 deg", so the phone is visible from the side. From a mirror camera it hides behind
    the hand: "live: P(phone) 0.00" (`docs/DATA.md`).
  - **Mouth classifier off.** Reason: on S01, v1 called the cup "food" and v2 called a turned bare
    face "food" (`docs/DATA.md` table). "3MDAD's 3/4 dashboard view and Open Images photos do not
    transfer to a frontal camera."
- **3MDAD details:** frames are mirrored; tracker sometimes locked onto the rear passenger (fixed).
  The 38 GB 3MDAD zip was deleted, keeping only front-view day RGB (session 2026-10-11 00:35).
- **Not available that day:** EBDD (waiting for the password), YawDD (not placed), SynDD (not
  received) (`docs/MORNING_REPORT.md`).
- **Camera placement report** (Topic 3 Word report, session 2026-10-11 20:25):
  - Centre rear-view mirror, 0.6–0.8 m from the face, turned 20–30° toward the driver, tilted
    5–15° down.
  - 1296×972 full field of view, never mirrored; NoIR + 850 nm IR LEDs at night.
  - The report marks distances/angles as design targets "to be confirmed in the car".

## Stage 7. 2026-10-16: PC reset; SynDD rear view becomes the main dataset

- **(reset period)** "My PC was reset and my local Claude Code project was lost" (session
  2026-10-16 02:23). D: (datasets) survived; Open Images intact ("17k images + labels"); EBDD zip
  on D: (0.97 GB) (session 2026-10-16 02:28–02:34).
- **SynDD (AI City 2024 Track 3, A1)** downloaded, **rear-view (mirror) camera only**:
  - 69 drivers, "~93 GB of the ~300 GB A1 zips". Time-stamped action segments.
  - Not mirrored; face mesh found the face in 98.5 % of 11,880 frames on one driver.
  - Fixed split 49 / 10 / 10 drivers (`docs/SYNDD_RETRAIN.md`, `configs/syndd_split.json`).
  - Why: it is the dataset with a mirror camera like ours (the 2026-10-16 brief: "SynDD (the
    rear-view-mirror dataset) ... use ONLY the rearview-mirror view").
- **EBDD** extracted: 13 drivers, colour, windshield view (`docs/DATA.md`).
- **Crop classifiers retrained on SynDD, all gray** (40 epochs, `docs/SYNDD_RETRAIN.md`):
  - **Data:** ear phone / hand_no_phone / none train 7,240 / 3,088 / 14,480; mouth drink / food
    / none train 1,434 / 624 / 2,868.
  - **Held-out SynDD drivers:**
    - Ear 160: phone P 0.983 / R 0.867; hand_no_phone 0.978 / 0.827; none 0.904 / 0.991;
      macro F1 0.921.
    - Mouth 96: drink 1.000 / 0.771; food 0.683 / 0.573; none 0.815 / 0.974; macro F1 0.794.
  - These classifiers later stayed **off by default** (`docs/DETECTOR_V2.md`: "stay in the code
    (`--mode full`), off by default").
- **Auto-labelled boxes on driver video** (SynDD, EBDD) with the teacher, kept only when they agree
  with the action label (commit `ec58c51`; `docs/DETECTOR_V2.md`).
  - The labelling log (`det_v2_syndd.log`, printed in session 2026-10-18 20:14) shows 1,653 SynDD
    clips. Frames per split: train 13,385, val 2,534, test 2,399 (total 18,318).
  - Train frames per action: phone right ear 2,207, left ear 2,217, phone in hand 2,803, drinking
    409, **eating 3**, normal 1,158, hand on head 975, singing 1,109, talking 2,033, yawning 471.
    No eating frames in val or test.
  - EBDD log (`det_v2_ebdd.log`, same message): train 1,514, val 210, test 369 frames (total 2,093).

## Stage 8. 2026-10-17: detector v2 (det_v2b → det_v2d), IR again

- **Detector v2 data** (`scripts/build_det_v2.py`, `docs/DETECTOR_V2.md`):
  - Sources: SynDD A1 rear (69 drivers, by driver), EBDD (13 drivers, by driver), Open Images
    (hand class dropped), Roboflow DMS_Project v2 and ADMS_FINAL_3 v1 (CC BY 4.0).
  - Roboflow images with boxes > 12 % (8 % for drink) of the image dropped (commit `883242c`).
  - 7,010 gray copies and 7,913 hand-occluded phone copies. Train 53.9k images.
- **det_v2a / det_v2b** (416 px): 7 epochs without Roboflow, then 35 more on the full set.
  - Phone found per frame on 10 test drivers (`docs/DETECTOR_V2.md`):

    | Model | Phone R ear | Phone L ear | Phone in hand | Normal (false) |
    |---|---|---|---|---|
    | stock yolo26n | 2.9 % | 3.5 % | 4.2 % | 0 % |
    | v1_416 | 7.1 % | 0.9 % | 9.8 % | 0 % |
    | v1_512 | 26.8 % | 34.5 % | 31.1 % | 21.7 % |
    | teacher yolo26m @1280 | 82.4 % | 79.2 % | 24.1 % | 6.9 % |
    | det_v2b @416 | 71.5 % | 91.6 % | 23.1 % | 0 % |

  - Per class on SynDD test: phone P 0.77 / R 0.67, AP50 0.78; drink 0.83 / 0.53, AP50 0.78.
    DMS_Project 0.97–0.99 AP50 "inflated by near-duplicates" (`docs/DETECTOR_V2.md`).
- **Overnight 2026-10-17** (`docs/OVERNIGHT_REPORT.md`):
  - **Step 1, honest test** (`eval_simple.py`, alert level, 10 fps): false alarms differ between
    driver groups (1.7 vs 36 /h). Half of the 36 came from one driver's sweatshirt print.
  - **Steps 2+3, label recovery + hard negatives → det_v2c: rejected.** Test phone false alarms
    13.7 /h vs 1.7.
  - **Step 4, det_v2d: IR-only (every image gray), 512 px, lr 0.002, 15 epochs, thresholds
    phone 0.40 / drink 0.45 / food 0.40 chosen on validation. Became the default** (commit
    `6467aef`). BEFORE (det_v2b @0.25) → AFTER (det_v2d), test drivers:

    | Behaviour | Before | After |
    |---|---|---|
    | Right ear | 85 %, 1.7 FA/h | 80 %, 0 FA/h |
    | Left ear | 100 % | 100 % |
    | Texting | 41 % | 37 % |
    | Drinking | 95 % | 90 % |

    Validation phone false alarms went from 36.1 to 5.2 /h. Eating 0 %.
  - **Ideas A–G** (tracking, temporal model, crop pass, A2 pseudo-labels, copy-paste, AI City
    winners, hard cases): **none beat det_v2d** (table in `docs/OVERNIGHT_REPORT.md` §7).
- **2026-10-17 afternoon, additions 1–8 and rules A/B** (`docs/OVERNIGHT_REPORT.md` §8):
  - **Dropped:**
    - SAM 2 boxes: val FA 5.2 → 20.6 /h.
    - SynDD dash + side views: FA 5.2 → 24.1 /h.
    - Eating rule B: 0–5 %.
  - **Kept:**
    - Per-class thresholds.
    - **Rule A (texting = head down + wrist low):** test texting 36.6 % → 41.5 % (46.3 % with
      warnings) at 1.7 false warnings /h.
  - **det_v2h (fisheye-trained):** better on simulated fisheye frames (phone AP50 0.795 vs 0.770).
    A trade-off on test, so kept as the alternative to try on the real camera.
  - **INT8 (ACIQ, mixed):** phone AP50 0.772 vs 0.771 FP32, 2.8 MB vs 9.3 MB, 22.6 vs 28.3 ms
    (laptop, 4 threads).
- **2026-10-18, 5-fold cross-validation by driver** (59 drivers, shorter 8-epoch recipe,
  `docs/OVERNIGHT_REPORT.md`):
  - Right ear 89 % (73–100), left ear 97 % (88–100), texting 65 % (58–75), drinking 66 % (52–79),
    eating 0 %.
  - Phone FA 9.0 /h (2.8–22.4).
  - Lesson: results "swing 10-25 points between driver groups".

## Stage 9. 2026-10-18/19: unseen-data tests and release

- **Unseen tests** (`docs/OVERNIGHT_REPORT.md` §9):
  - **3MDAD** (50 drivers, colour → gray, 650 clips): calls right 80 % / left 92 %; texting right
    hand 96 % / left hand 16 %; drinking 80 % / 68 %; false phone alert on 8 % of normal clips.
  - **DAD** (real IR, 3 drivers, 66 min normal driving): calls 4/5, texting 5/6, drinking 2/2,
    **69 false phone alarms /h** (steering wheel read as a phone).
- **Release 2026-10-19** (commit `2292523`): det_v2d FP32 / INT8 / ONNX, det_v2h, YOLO26n-pose
  shipped in git (`models/distraction/models/README.md`). Pi 5 numbers "still to be measured
  with all models running" (same file).
## Stage 9b. 2026-10-18: Task 6 and Task 7 rewritten as version 2; release PR

- **What:** the user attached `Task 6 - Dataset Preparation and Preprocessing.docx` and
  `Task 7 - Dataset and Test-Scenario Plan.docx` from Downloads (session 2026-10-18 20:07). Both
  were "redone as version 2: same cover, colours, tables and layout as your originals ... with
  the real numbers", saved next to the originals (session 2026-10-18 20:23). So version 1 of
  both existed by 2026-10-18; its content is NOT FOUND.
- **Where the Task 6 v2 numbers came from:**
  - The tables were rebuilt from the data-build logs on D: (session 2026-10-18 20:14), and the
    charts used numbers typed into the chart script (session 2026-10-18 20:16).
  - What can be recomputed from the log text in the transcript is in `report_vs_project.md`
    section 3.
- **Release:** the IR detector, docs and experiment scripts were packaged for GitHub (session
  2026-10-18 21:00–21:16). Opened as
  [ziadteama/RTDMS#3](https://github.com/ziadteama/RTDMS/pull/3): 63 commits, 141 files, all in
  `models/distraction/` (session 2026-10-18 21:32). First commit of the Task 6/7 v2 files:
  `2292523` (git date 2026-10-19 00:17).
- **2026-10-19 → 10-25:** almost no activity in the transcripts. The next message is
  2026-10-25 20:30.

## Stage 9c. 2026-10-25: det_v2d live on the Pi, and the near-ear problem

This stage is the reason we moved from the box detector to the action classifier.

- **Setup** (session 2026-10-25 20:30–23:31):
  - The Pi was connected by Ethernet; the release detector was bundled for the Pi (85 MB,
    INT8 `det_v2d_ir_512_det_aciq_mixed_ncnn_model` plus the FP32 fallback).
  - Camera: the Pi lists `ov5647 [2592x1944 10-bit GBRG]` (session 2026-10-25 23:30).
  - Stream: "picamera2 YUV420/Y 1296x972 -> view 640x480; detector ... det_v2d ... INT8;
    drowsiness on; texting rule off" (session 2026-10-25 23:30).
- **Speed on the Pi:**
  - Detector every 2nd frame and pose every 6th frame: **24.5 FPS at 58 °C**, no errors (session
    2026-10-25 21:29).
  - The user then asked for "both the ir and the drowsiness percelos thing only", so pose was
    dropped (session 2026-10-25 23:21).
  - Power: the Pi rebooted and the Ethernet link dropped several times that evening, on the
    official 27 W supply (session 2026-10-25 21:27–23:30).
- **The failure the user reported:** "how is this not detected it detects good on far ear but
  near ear its bad" (user, session 2026-10-25 23:40).
- **Measured on that recording** (det_v2d phone score per frame, session 2026-10-25 23:48):

  | Segment | Frames | Median phone score | Frames ≥ 0.40 | Alert rule fires (score ≥ 0.25) |
  |---|---|---|---|---|
  | Far ear (16–34 s) | 180 | 0.63 | 93 % | 89 % of the time |
  | Near ear (40–82 s) | 420 | 0.18 | 13 % | 11 % of the time |

- **Fix tried: an "ear-zone" rule** (lower phone threshold near the ear, held 2 s). Scored once
  on the SynDD test drivers (session 2026-10-25 23:48):

  | Setting | Right ear | Left ear | Texting | Drinking | Phone FA/h |
  |---|---|---|---|---|---|
  | Baseline det_v2d | 80 % | 100 % | 36.6 % | 90 % | 0 |
  | Ear rule, conf 0.20 | 90 % | 100 % | 36.6 % | 90 % | 3.4 |
  | Ear rule, conf 0.25 or 0.30 | 80 % | 100 % | 36.6 % | 90 % | 1.7 |

- **Explanation given at the time:** "Near-ear calls are missed because your hand hides the
  phone: confidence is about 0.18 versus 0.63 at the far ear. An ear-zone rule lifts SynDD
  near-ear calls from 80% to 90% at about 3 extra false alarms per hour; fine-tuning on your own
  clips is the real fix" (session 2026-10-25 23:48).
- **Datasets on D: listed that night** (session 2026-10-26 00:03–00:04):
  - SynDD A1 146 GB: 69 driver folders; rear view 138 videos (86 named `Rear_view`, 52 named
    `Rearview`); dashboard 40; right side window 40.
  - SynDD A2 21 GB: **15** entries in the folder.
  - DMS_Project 1.5 GB, ADMS_FINAL_3 265 MB, EBDD 2.0 GB, 3MDAD 3.9 GB, DAD 18 GB, Open Images
    2.9 GB, COCO 1.8 GB (not used for training).
  - The suggestion for the near-ear problem: 3MDAD is "the best unused source for near-ear
    hand-over-phone examples ... We'd lose it as an unseen test set, though, unless we split it by
    driver (say 35 train, 15 test)."
- **Decision, 12 minutes later:** the action-classifier brief (session 2026-10-26 00:16). It
  asks to:
  - "Replace the phone/drink/eat OBJECT detector with an ACTION approach";
  - not alert "when a hand just rests on the cheek/ear/chin with no phone";
  - run "≥15 FPS on Raspberry Pi 5 together with face mesh";
  - split 3MDAD 35 train / 15 test.

  The brief does not state its reason in its own words. The near-ear analysis and the 3MDAD
  suggestion right before it are the recorded context.

## Stage 10. 2026-10-26: action classifier (v1), then hybrid v2

- **Brief (session 2026-10-26 00:16):** "Replace the phone/drink/eat OBJECT detector with an
  ACTION approach ... does NOT alert when a hand just rests on the cheek/ear/chin with no phone
  ... runs ≥15 FPS on Raspberry Pi 5". "Do NOT use: SynDD dashboard/side views, SynDD A2, COCO."
- **Data** (`action_v1/REPORT.md`, `PROGRESS.md`):
  - SynDD A1 rear 52,125 frames (49/10/10).
  - syndd_fish 6,188 (train).
  - **3MDAD front RGB→gray 60,655 frames, 35 train / 15 test drivers (seed 0)**.
  - EBDD → gray 5,972 (test: akkas, jewel).
  - DAD part 1 IR 11,349 (test only).
  - Sampling 2.5 fps, 0.5 s dropped at each segment edge. Balanced train set 62,085 crops (no
    class > 3× eating, 3,989).
- **v1 = act_n224** (yolo26n-cls, 224 px, 7 classes) + phone_n128 ear check:
  - Frame accuracy: SynDD-test 0.67, 3MDAD-test 0.68, EBDD-test 0.41, DAD 0.10.
  - Calls on SynDD-test 37/39 vs release 34/39.
  - False alarms on normal + hand-on-face: SynDD 14.5 /h vs release 0 (`action_v1/REPORT.md`).
- **Rejected:** yolo26s-cls: "not better ... ~3x slower" (D15). Talking check: never added
  recall (D13).
- **v2 hybrid** (`action_v1/REPORT_v2.md`):
  - Lap phone check fine-tuned: AUC 0.84 vs 0.49 (D18).
  - Drinking / eating from det_v2d boxes near the mouth (D17).
  - Smoking class tried and **rejected** (D21).
  - Detector every 2nd frame for Pi speed (D22).

  | Test set | Release det_v2d | v2 |
  |---|---|---|
  | SynDD calls / texting / drinking / FA/h | 34/39, 14/41, 15/18, 0 | 37/39, 18/41, 15/18, 0 |
  | 3MDAD calls / texting / drinking / FA/h | 24/30, 17/30, 22/30, 14.2 | 30/30, 24/30, 22/30, 19.6 |
  | DAD calls / texting / drinking / FA/h | 4/5, 5/6, 2/2, 79.2 | 5/5, 4/6, 2/2, 3.6 |

- **INT8 (KL)** loses < 0.3 points (`action_v1/REPORT_v2.md`).
- **Pi speed (estimates, not measured):** "The Pi was not connected, so these are estimates"
  (`action_v1/REPORT_v2.md`). Detector every 2nd frame: 44 ms worst / ~38 ms typical.
- **Same day on the Pi** (session 2026-10-26 08:35):
  - v2 running live with face mesh + PERCLOS "at about 30 FPS", box detector off.
  - Camera upside down, rotated 180°.
  - The Pi restarted three times; power supply "official 27 W, 5.1 V, no throttling".

## Stage 11. 2026-11-07 → 11-09: Garmin; v2 pushed to main; Pi start script

- Garmin FR265 HR/RR stream to the Pi (physiology; commits `e8ddaee` … `a482795`). Not Task 6
  scope.
- **2026-11-08:**
  - v2 phone model and the Pi stream committed (`981a822`) and branches merged into main via
    [ziadteama/RTDMS#1](https://github.com/ziadteama/RTDMS/pull/1) to
    [ziadteama/RTDMS#7](https://github.com/ziadteama/RTDMS/pull/7) (git log).
  - Pi runs `pi/start_stream.sh`: `--hybrid --no-detect --no-texting --mesh --rotate 180`.
  - "About 15 ms per frame of model time on the Pi, with the stream at ~30 FPS (the camera's
    limit)"; **no drinking or eating alerts** on the Pi (session 2026-11-08 20:01).
- **Why the Pi gives no drinking or eating alerts:**
  - In v2, drinking and eating come **only** from the det_v2d box detector. The action model is
    not used for them (`action_v1/DECISIONS.md` D17).
  - The Pi stream starts with `--no-detect`, so the detector never runs (`pi/start_stream.sh`).
  - The trade-offs recorded for leaving it off:
    - The full hybrid with the detector on every frame is estimated at 66 ms per frame on the
      Pi (15.1 FPS worst case), "no margin above 15 FPS" (`action_v1/DECISIONS.md` D22, an
      estimate).
    - Turning it back on every 2nd frame "costs about 22 ms per frame on the Pi ... the rate
      drops to roughly 20 FPS. It also brings back its own false phone alerts, about 79 per hour
      on the IR test set" (session 2026-10-26 08:35).
  - No message states the decision to leave it off in so many words. The v2 report itself
    proposed det_v2d boxes for drinking and eating, with the detector every 2nd frame
    (`action_v1/REPORT_v2.md`).
  - The newer drinking model (stage 12) was never exported for the Pi or installed. The INT8/NCNN
    export was blocked on the PC and the Pi was unreachable (session 2026-11-14 16:17).
  - Eating has no working model at all (stage 12).

## Stage 12. 2026-11-08 → 11-15: held-object drinking model (current best drinking model, not on the Pi)

- **Why:** "labels was bad can we do something related to holding an object + near face" (user,
  session 2026-11-08 20:56). The box labels came from a teacher model that "rarely saw food".
- **Branch:** `phone/held-object`, later `overnight/held-object` (last commits named: `9430ae5`,
  `e8b4761`, `bde27ab`, `47b0774`, `b246d11`). "Nothing was pushed" (session 2026-11-14 06:27).
  - You said on 2026-11-16 that you pushed it. A fetch of `ziadteama/RTDMS` on 2026-11-16
    found no such branch and none of these commits. The other repos this account can reach
    have nothing either. So the numbers below are from the transcript only.
  - Your decision: count IR-3 as the **current best drinking model**. It is **not set up on the
    Pi yet**.
- **Data** (session 2026-11-13 23:07):
  - 22,612 hand-at-mouth crops, 95 training drivers + 10 SynDD validation drivers, no test
    drivers.
  - Cup/bottle 2,459 tight / 4,614 wider (1,960 tight ones from 3MDAD): "clean".
  - Empty hand 8,406 / 12,837: "clean".
  - Food 597 / 1,161: "not clean" (food visible in about 7 of 48).
- **Dataset inventory of D:** (2026-11-14, `dataset_inventory.md` on the unpushed branch):
  - On disk but unused: SynDD dashboard/side views, SynDD A2 (no labels), Drive&Act NIR videos
    (annotations missing), AUC v1/v2, DAD top_IR, MRL Eye, UTA-RLDD Fold3 part 2.
  - Missing: DAD parts 2…N, Drive&Act annotations, DMD, 3MDAD night IR / side view, 100-Driver,
    State Farm.
- **IR test set (frozen, driver-disjoint):** 20 drinking and 19 eating events, below the 30 + 30
  target, because "the extra IR data isn't on the D: drive" (session 2026-11-14 16:17).
- **Drinking results** (validation decides; test is report-only):

  | Model | SynDD | 3MDAD | DAD (real IR) | Source |
  |---|---|---|---|---|
  | First model (old labels) | 12/18, 14.5 /h | 29/30, 5.3 /h | 2/2, 0.9 /h | session 2026-11-14 01:44 |
  | v2 cleaned labels, larger "s" model | 12/18, 0 /h | 28/30, 7.1 /h | 1/2, 1.8 /h | session 2026-11-14 01:57 |
  | Best small model + phone veto (trimmed windows) | 12/18, 0 /h | 29/30, 2.4 /h | 0/2, 0 /h | session 2026-11-14 06:27 |
  | Old box detector (same windows) | 15/18, 0 /h | 22/30, 5.2 /h | 2/2, 8.7 /h | session 2026-11-14 06:27 |
  | **IR-3 (+1,500 phone-in-hand hard negatives), untrimmed IR test** | **16/18, 1.07 /h** | — | **2/2, 1.58 /h** | session 2026-11-14 21:24 |
  | Old box detector, untrimmed IR test | 16/18 | — | 2/2, 8.7 /h | session 2026-11-14 21:24 |

  - IR-3 was **kept** (validation 13/15 at 0 /h vs previous best 14/15 at 1.09 /h, session
    2026-11-14 21:14).
  - Reverted: camera simulation, all phone hard negatives (recall 14 → 12 of 15), yawn block,
    stronger augmentation, extra cup weight (sessions 2026-11-14 06:27, 17:31).
- **Eating:** no model. There are no hand-checked food labels yet; the hand-to-mouth + chewing
  rule caught 0/19 on SynDD test (session 2026-11-14 06:27). An eating temporal head was being
  trained on IR-3 features at the last message; its result is NOT FOUND (session ends 2026-11-15
  01:06).
- **Blocked:** the Pi did not answer SSH. Windows Application Control blocked `ncnn` on the PC,
  so there is no INT8/NCNN export of the drinking model (session 2026-11-14 16:17).

---

## Models: every model tried, in order

| Date | Model | Data | Key numbers (source) | Decision |
|---|---|---|---|---|
| 08-28 | MediaPipe FaceLandmarker + EAR rules | none (pre-trained) | Pi: 30 FPS, 13.5 ms (EVIDENCE face, 10-09) | **Kept** (face model today) |
| 08-28 | COCO yolov8n / v8s / 11n / 11x (no training) | own webcam clip | phone frames 38 / 44 / 28 / 45 of 210 (session 08-28) | Keep nano, fine-tune later |
| 09-25 | YOLOv8n-cls State Farm (HF) | State Farm (pre-trained) | not measured on hold-out (phone EVIDENCE) | Dropped for the IR camera (wrong view) |
| 10-10 | yolo26n v1_416 / v1_512 | Open Images converted | phone AP50 0.86 / 0.87 on OI test; S01 phone at ear 0.00 | Dropped (does not transfer) |
| 10-11 | ear / mouth crop classifiers (yolo26n-cls) | 3MDAD + Open Images | ear phone P/R 0.963/0.905 | Turned off (camera angle) |
| 10-16 | ear / mouth crop classifiers, SynDD gray | SynDD + EBDD + 3MDAD + OI | ear macro F1 0.921, mouth 0.794 | Off by default |
| 10-17 | det_v2b @416 | merged_b (5 sources) | phone R ear 71.5 %, L ear 91.6 % per frame | Replaced by det_v2d |
| 10-17 | det_v2c (hard negatives) | + hard negatives | test FA 13.7 /h vs 1.7 | Rejected |
| 10-17 | **det_v2d** IR 512 | merged_b, gray | test calls 80 % / 100 %, 0 FA/h; drinking 90 % | **Release model**, but **off** on the Pi now |
| 10-17 | det_v2h fisheye | + 6,718 fisheye frames | phone AP50 0.795 on fisheye frames | Alternative for the real camera |
| 10-17 | det_v2i (3 SynDD views) | + dash / side | val FA 24.1 /h | Rejected |
| 10-26 | act_n224 (v1) | SynDD + 3MDAD + EBDD | SynDD FA 14.5 /h | Superseded by v2 |
| 10-26 | act_s224 | same | ~3× slower, not better | Rejected |
| 10-26 | act_n224_smk (smoking class) | + 3MDAD smoking | smoking FAs 7 → 7 | Rejected |
| 10-26 | **v2 hybrid** (act_n224 + phone_ear + phone_lap, INT8) | as above | DAD FA 3.6 vs 79.2 /h | **Runs on the Pi now** |
| 11-14 | **IR-3 held-object drinking model** | hand-at-mouth crops | IR test 18/20 drinking | Best drinking result; **not pushed, not on the Pi** |

## Datasets: every dataset used, considered or dropped

| Dataset | Source | Size (as recorded) | IR / RGB | Camera | Role | Kept / dropped and why |
|---|---|---|---|---|---|---|
| UTA-RLDD | Project 1 | Fold3 part 2 on D: (6 drivers, 7.6 GB) | RGB | phone camera, front | planned for drowsiness | Not used (INVENTORY: "not relevant") |
| MRL Eye | Project 1 | 383 MB on D:; 84,898 images, 37 people (from old report, not verified) | IR | eye crops | eye-state CNN (done outside Claude Code) | Files lost in the reset; not counted in results |
| CEW | Project 1 (reviewed) | 2,423 photos (from old report, not verified) | RGB | faces | face-model thresholds + test (done outside Claude Code) | Files lost in the reset; not counted in results |
| DG-Unicamp | Project 1 | — | — | — | planned gaze | NOT FOUND (never mentioned after Project 1) |
| WESAD | Project 1 | 15 subjects | physiology | — | physiology fatigue model | Used by physiology (commit `fd13c61`) |
| State Farm | Kaggle | not on D: | RGB | passenger side | v1 phone model (pre-trained weights) | Dropped: wrong view |
| AUC v1/v2 | request | ~44 drivers, on D: | RGB | side | — | Not used: passenger-side view (DATA) |
| Open Images V7 | public | 16,996 downloaded = 14,674 train / 1,143 val / 1,179 test (download log, session 2026-10-18 20:14); v1 converted set: train 13,623 | RGB photos | none | detector training | **Used** (det_v2d) |
| 3MDAD Day-RGB2 front | Kaggle | 50 drivers, 16 actions, ~3 fps | RGB → gray | low dashboard, 30–45° | crop classifiers, unseen test, action training | **Used**: test for det_v2d, train/test for the action model |
| 3MDAD night IR / side | authors | — | IR | — | — | Missing (not on D:) |
| EBDD | BUET | 13 drivers, 2.0 GB; 2,093 labelled frames (log) | RGB → gray | windshield / side | detector + action training, test | **Used** |
| SynDD A1 rear view | AI City 2024 Track 3 | 69 drivers, 138 rear-view videos, 30 fps 1920×1080; 18,318 labelled frames from 1,653 clips (log) | Pixel check (2026-11-14): mean colour 0.1 = "monochrome / NIR-sensitive (daylight, not active IR)". The repo docs and the old report call it infrared | rear-view mirror | main training + test | **Used** (main dataset) |
| SynDD A1 dash / right views | same | 20 drivers downloaded | same | dashboard, side window | detector training test | Dropped: FA 5.2 → 24.1 /h |
| SynDD A2 | same | 21 GB; 15 entries in the folder listing (session 2026-10-26 00:03) vs "10 drivers" (INVENTORY 2026-11-14), conflicting; 30 videos (OVERNIGHT) | same | rear | pseudo-labels | Dropped: noisier, more FA |
| Roboflow DMS_Project v2 | Roboflow | 10,198 kept after filters: from old report, not verified (typed as 7,244 / 2,121 / 833 in the 2026-10-18 chart script; no log line seen) | IR + colour | DMS | detector training | **Used** (filtered) |
| Roboflow ADMS_FINAL_3 v1 | Roboflow | 2,698 kept after filters: from old report, not verified (typed as 2,149 / 549 / 0 in the chart script) | colour | in-car | detector training | **Used** |
| DAD part 1 | TU Munich | 3 drivers, 224×171, 45 fps | real IR | front + top | test only | **Used** (test only); parts 2…N missing |
| Drive&Act | registration | 15 drivers, NIR videos on D: | NIR | inner mirror, wheel | — | Not used: annotation files missing |
| DMD | request | — | IR + RGB | — | planned night test | Missing (requested) |
| 100-Driver | request | — | incl. NIR | 4 cameras | planned | Missing (requested) |
| YawDD | request | — | — | mirror set | planned false-alarm data | Never placed on disk |
| S01 (developer webcam) | own | 1 clip, 92 s (EVIDENCE) | RGB | laptop front-right | test only | Used as a smoke test |
| Own Pi-camera recordings | own (Task 7) | none yet | — | centre mirror | planned test | Not recorded yet |

## Hardware and setup changes

| Date | Change | Why | Source |
|---|---|---|---|
| May 2026 | Plan: Pi 5 8 GB + AI HAT+ 26 TOPS + Pi IR camera 5MP 160° | Project 1 BOM | `CLAUDE.md` |
| 08-28 | Laptop webcam for all tests | No Pi camera yet | sessions 08-28 |
| 10-09 | OV5647 RGB stand-in camera on the Pi, 640×480 @ 30 fps for face | Development until the IR module arrives | PI_TARGET Camera |
| After 10-10 (exact date not recorded) | IR NoIR 160° camera module installed on the Pi, replacing the RGB stand-in | The BOM's IR camera | your answer, 2026-11-16 |
| 10-09 | Face runs on LiteRT, not MediaPipe | MediaPipe does not run on the Pi's Python 3.13 | session 10-09 |
| 10-11 | Target switched to laptop colour webcam; IR parked | Live testing | LAPTOP_TESTING |
| 10-11 | Placement target: centre mirror, 0.6–0.8 m, 20–30°, NoIR + 850 nm LEDs | Placement report | session 10-11 |
| 10-17 | Back to IR: detector trained gray-only | Match the IR mirror camera | OVERNIGHT §3 step 4 |
| 10-25 | det_v2d INT8 on the Pi: detector every 2nd frame, pose every 6th → 24.5 FPS at 58 °C; camera listed as `ov5647`, captured 1296×972 → 640×480 view; picture "nearly black", needs light or the IR LEDs | Lower load for the Pi | session 10-25 21:29, 23:20, 23:30 |
| 10-26 | Camera mounted upside down → stream rotated 180°; Pi on Ethernet hub; reboots seen | — | session 10-26 |
| 11-08 | Pi profile: rectification off (camera not calibrated), INT8 detector, LiteRT face mesh | Speed; no calibration yet | `configs/profiles/pi.yaml` |
| 11-14 | Pi unreachable; PC blocks `ncnn` | — | session 11-14 |

## Questions for me

Resolved on 2026-11-16:
- **Reset:** only one, before 2026-10-16.
- **CEW / MRL Eye:** done outside Claude Code; files lost; old-report numbers, not counted.
- **Camera:** IR NoIR 160° installed after 2026-10-10 (date not recorded).
- **Held-object:** IR-3 counts as the current best drinking model, not on the Pi.
- **Eating frames:** 3 (log, training set only).
- **SynDD A2:** both values kept with a note.
- **SynDD modality:** as the pixel check found it.

Still open:
1. **Held-object branch:** not found on GitHub (see stage 12). Which repo or remote did you
   push it to?
2. **Why YOLO26n** replaced the YOLOv8n plan on 2026-10-10: NOT FOUND.
3. **Eating temporal head (2026-11-14/15):** did it finish, and with what numbers?
4. **Iris landmarks:** 478 with iris or 468 without (sessions 08-28 disagree)?
5. **Hand check of the 495 test frames:** was it ever done?
