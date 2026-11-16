# Task 6 report vs the project as it is now

Compared: `Task 6 - Dataset Preparation and Preprocessing (v2).pdf` (in this folder; cover says
"October 2026 (version 2)"; first committed in `2292523` on 2026-10-19) against the repo on
`main` (last commit `fd13c61`, 2026-11-13) and the saved Claude Code session transcripts.

Status values: **OUTDATED** (the project changed), **MISSING FROM REPORT** (exists in the project,
not in the report), **STILL CORRECT**, **CANNOT VERIFY** (no file, log or transcript I could read
backs it up or contradicts it).

Source short names:
- `README` = `models/distraction/README.md`; `MODELS` = `models/distraction/models/README.md`
- `DATA` = `docs/DATA.md`; `DETV2` = `docs/DETECTOR_V2.md`; `OVERNIGHT` = `docs/OVERNIGHT_REPORT.md`;
  `EVIDENCE` = `docs/EVIDENCE.md`; `MORNING` = `docs/MORNING_REPORT.md`; `SYNDD_RT` = `docs/SYNDD_RETRAIN.md`
- `AV1/...` = `models/distraction/action_v1/` (`REPORT.md`, `REPORT_v2.md`, `DECISIONS.md`, `PROGRESS.md`)
- `PI_TARGET` = `Subsystems/Raspberry Pi 5 Target.md`; `FACE_EV` = `models/face/docs/EVIDENCE.md`
- `session YYYY-MM-DD` = a Claude Code session transcript on that date (times UTC)
- `LOGS 10-18` = data-build log output printed in session 2026-10-18 20:14 (`build_openimages.log`,
  `build_det_v2b.log`, `det_v2_syndd.log`, `det_v2_ebdd.log` on D:). The D: drive is not on this
  machine, so these logs are the closest thing to a direct count I could check
- `INVENTORY` = `models/distraction/action_v1/dataset_inventory.md` (written 2026-11-14, merged to main in
  [ziadteama/RTDMS#10](https://github.com/ziadteama/RTDMS/pull/10) on 2026-11-16)
- `IRR` = `action_v1/ir_report.md`; `IRL` = `action_v1/ir_log.md`; `HELD` = `action_v1/HELD_OBJECT.md` (all from PR #10)

## 1. Datasets used

| Topic | What the report says | What the project has now | Source | Status |
|---|---|---|---|---|
| Detector training sources | 5 sources: SynDD, Open Images V7, DMS_Project, ADMS_FINAL_3, EBDD | Same 5 sources for the release detector det_v2d | MODELS (det_v2d model card), DETV2 | STILL CORRECT |
| Datasets used by the model that runs on the Pi | Report only describes the YOLO26n box detector | The Pi stream runs the **v2 action classifier** (`--hybrid --no-detect`). Its training data: SynDD A1 rear (49/10/10 drivers), det_v2 syndd_fish, **3MDAD front RGB→gray (35 train / 15 test drivers)**, **EBDD→gray**, DAD part 1 (test only). The phone checks use Open Images, DMS_Project v2, ADMS_FINAL_3 and det_v2 phone boxes (9,626 phone crops) | `pi/start_stream.sh`, AV1/REPORT.md "Data used", AV1/DECISIONS D5–D6 | MISSING FROM REPORT |
| 3MDAD role | "Test only" | Still test only **for det_v2d**. Before that, 3MDAD front view trained the ear/mouth crop classifiers (2026-10-11). From 2026-10-26 it is also **training data** for the action classifier (35 drivers, seed 0) | DATA (Sources table), MORNING, AV1/DECISIONS D6, `action_v1/splits/3mdad.json` | OUTDATED |
| DAD role | Test only; 3 drivers, 66 min normal driving | Test only for every model. 3 drivers (Tester1, 10, 11), part 1 of the archive only | OVERNIGHT §9, AV1/class_map.json, INVENTORY | STILL CORRECT |
| EBDD role | Training + test, 2 drivers kept for test | Same for det_v2d. In the action classifier its 2 validation drivers (aktar, asif) moved into training; test drivers akkas and jewel | DETV2, AV1/DECISIONS D5 | STILL CORRECT (with one change for the action model) |
| Face datasets | CEW (2,423 photos) for thresholds and test; MRL Eye (84,898 IR images, 37 people) to train an eye-state CNN | Done outside Claude Code; the original files were lost in the PC reset (your answer). No code or results in the repo. MRL Eye is still on D:, listed as not used | your answer 2026-11-16, INVENTORY | CANNOT VERIFY: from old report, not verified; not counted in results |
| Held-object (drinking / eating) data | — | Hand-at-mouth crops: 22,612 from training drivers and SynDD validation drivers, no test drivers (cup / bottle 2,459 tight, mostly 3MDAD; empty hand; food 1,161 "not clean"). Infrared split `ir_split.json`: train SynDD 49, val SynDD 10, test SynDD 10 + DAD 3 (20 drinking, 19 eating events) | HELD, IRR §1 | MISSING FROM REPORT |

## 2. Datasets dropped or not used

| Topic | What the report says | What the project has now | Source | Status |
|---|---|---|---|---|
| State Farm | Dropped: passenger-side colour photos, wrong angle | Same. Note: the State Farm data itself is not on D: (listed as "Missing" on 2026-11-14). Only pretrained weights from Hugging Face were used (`models/phone`) | DATA, `models/phone/docs/EVIDENCE.md`, INVENTORY | STILL CORRECT |
| AUC Distracted Driver | Not mentioned | Not used (passenger-side view). AUC v1/v2 **is on D:** (about 44 drivers, RGB, side view) but unused | DATA, `models/phone/docs/ARCHITECTURE.md` ("deferred"), INVENTORY | MISSING FROM REPORT |
| SynDD dashboard + side views | Not kept: phone false alarms 5 → 24 /h | 5.2 → 24.1 /h on validation (det_v2i) | OVERNIGHT §8 addition 2 | STILL CORRECT |
| SynDD A2 | "15 unlabelled drivers", not kept | Folder listing on 2026-10-26: `ls public/syndd/A2 | wc -l` = **15**, 21 GB. OVERNIGHT: 30 videos, 21.5 GB, 9,231 frames pseudo-labelled, not kept. Commit `5c8e21b`: "the 15 unannotated drivers". INVENTORY (2026-11-14): **10 drivers** | session 2026-10-26 00:03, OVERNIGHT §7 D, git `5c8e21b`, INVENTORY | CANNOT VERIFY (conflicting: 15 vs 10; I could not recount) |
| YawDD | Not mentioned | Planned as background / false-alarm data; never placed on disk | DATA (Sources), MORNING ("not placed") | MISSING FROM REPORT |
| DMD, 100-Driver | Not mentioned | "Requested" (DATA); on 2026-11-14 still missing, with request pages listed | DATA, INVENTORY | MISSING FROM REPORT |
| Drive&Act | Not mentioned | NIR videos are on D: (15 drivers, inner mirror + steering wheel) but the **annotation files are missing**, so unused | INVENTORY | MISSING FROM REPORT |
| 3MDAD night (IR) / side view | Not mentioned | Not on disk. Only Day-RGB2 front was kept; the 38 GB 3MDAD zip was deleted on 2026-10-11 | INVENTORY, session 2026-10-11 | MISSING FROM REPORT |
| Planned Project 1 datasets | Not mentioned | Project 1 picked UTA-RLDD, AUC, MRL Eye, DG-Unicamp, WESAD. UTA-RLDD (Fold3 part 2) and MRL are on D: but unused for vision; WESAD is used by the physiology subsystem | `CLAUDE.md` (Datasets), INVENTORY, git `fd13c61` | MISSING FROM REPORT |
| Ear / mouth crop classifiers and their data | Not mentioned | Built 2026-10-11 (3MDAD + Open Images) and retrained 2026-10-16 (SynDD gray); then left off by default (`mode: full` only) | MORNING, SYNDD_RT, DETV2 ("stay in the code ... off by default") | MISSING FROM REPORT |

## 3. Dataset sizes and classes

| Topic | What the report says | What the project has now | Source | Status |
|---|---|---|---|---|
| Detector classes | 0 phone, 1 drink, 2 food | Same | MODELS | STILL CORRECT |
| Detector training size | 53,889 training images | 53,889 | MODELS, DETV2 ("53.9k") | STILL CORRECT |
| Gray copies / hand-pasted copies | 7,010 / 7,913 | 7,010 / 7,913 | DETV2, MODELS | STILL CORRECT |
| Image counts per split (Table 7: train 53,889, val 6,557, test 4,780) | As in Table 7 | **Recomputed, they add up.** Per source (SynDD / Open Images / DMS_Project / ADMS / EBDD): train 13,385 + 14,674 + 7,244 + 2,149 + 1,514 = 38,966, plus 7,010 gray copies and 7,913 occluded copies = **53,889**; val 2,534 + 1,143 + 2,121 + 549 + 210 = **6,557**; test 2,399 + 1,179 + 833 + 0 + 369 = **4,780**. SynDD, Open Images and EBDD counts and the copy counts are in LOGS 10-18. The DMS_Project and ADMS counts appear only as numbers typed into the chart script (session 2026-10-18 20:16) | LOGS 10-18, session 2026-10-18 20:16 | STILL CORRECT (DMS_Project / ADMS parts: from old report, not verified) |
| Box counts per class (Table 7: e.g. train phone 30,193, drink 47,605, food 24,786; "no object" counts) | As in Table 7 | Only the SynDD part is in a log (e.g. SynDD train phone boxes 7,227, drink 476, food 54). The totals appear only as typed numbers in the chart script | LOGS 10-18, session 2026-10-18 20:16 | CANNOT VERIFY: **from old report, not verified** |
| SynDD frames (18,318 from 1,653 clips) and per-action counts (Table 8) | As in Tables 4 and 8 | **Recomputed from the labelling log, all match.** 1,653 clips; frames train 13,385 + val 2,534 + test 2,399 = 18,318. Train per action: ears 2,207 + 2,217 = 4,424; phone in hand 2,803; drinking 409; eating 3; normal 1,158; look-alikes 975 + 1,109 + 2,033 + 471 = 4,588 | LOGS 10-18 (`det_v2_syndd.log`) | STILL CORRECT |
| Open Images size | 16,996 photos | **Recomputed: 14,674 + 1,143 + 1,179 = 16,996** (download log) | LOGS 10-18 (`build_openimages.log`) | STILL CORRECT |
| DMS_Project / ADMS_FINAL_3 sizes | 10,198 / 2,698 images | Sums of the per-split numbers typed in the chart script (7,244 + 2,121 + 833; 2,149 + 549 + 0). No log line with these totals was seen. Raw export folder counts printed on 2026-10-18: DMS_Project train 17,126 / valid 4,893 / test 2,447; ADMS train 6,484 / valid 1,621 (the listing does not show whether it counted images or all files) | session 2026-10-18 20:14–20:16 | CANNOT VERIFY: **from old report, not verified** |
| EBDD frames | 13 drivers, 2,093 frames | **Recomputed: 1,514 + 210 + 369 = 2,093** | LOGS 10-18 (`det_v2_ebdd.log`) | STILL CORRECT |
| Eating frames in SynDD | 3 frames | **3, in the training set only** (labelling log; none in val or test). OVERNIGHT §8 says 5; the log value is used | LOGS 10-18 | STILL CORRECT |
| Action classifier data | — | 7 classes (normal, call, texting, drinking, eating, hand_on_face, other). Frames: SynDD 52,125, 3MDAD 60,655, EBDD 5,972, DAD 11,349, syndd_fish 6,188. Balanced train set 62,085 crops | AV1/PROGRESS.md, AV1/REPORT.md, `class_map.json` | MISSING FROM REPORT |
| 3MDAD size | 50 drivers, 16 actions, 650 clips | 50 drivers; 13 actions × 50 = 650 clips in the unseen test; ~3 fps frames, 640×480 | OVERNIGHT §9, INVENTORY | STILL CORRECT |

## 4. IR vs RGB

| Topic | What the report says | What the project has now | Source | Status |
|---|---|---|---|---|
| SynDD modality | "Acted driving video, infrared" | **Pixel check (2026-11-14):** mean colour difference 0.1 on sampled frames = "grey ... monochrome / NIR-sensitive (daylight, not active IR)". The repo docs and the old report called it infrared | INVENTORY; DATA, SYNDD_RT | OUTDATED (report the pixel check; note the docs said infrared) |
| DMS_Project | "IR and colour" | "IR + colour DMS" | DETV2 | STILL CORRECT |
| Detector input look | Every image gray; half get camera effects | det_v2d trained gray-only at 512 px; `--look ir` "trains every image gray (half also get the IR traits)" | git `3a90ef9`, MODELS | STILL CORRECT |
| Target camera look during development | IR only | 2026-10-11 the target was briefly the **colour laptop webcam** (`data.yaml: look: color`); IR came back with det_v2d on 2026-10-17. `configs/data.yaml` still says `look: color` | DATA, `configs/data.yaml`, LAPTOP_TESTING | MISSING FROM REPORT |

## 5. Splits

| Topic | What the report says | What the project has now | Source | Status |
|---|---|---|---|---|
| SynDD | By driver 49 / 10 / 10 | Same, fixed in `configs/syndd_split.json` | `syndd_split.json`, SYNDD_RT | STILL CORRECT |
| Open Images / Roboflow | Their own published splits | Same. DMS_Project split is image-level, so its scores are inflated | DETV2 | STILL CORRECT |
| CEW 30 % tuning / 70 % test; MRL split by person | As stated | Files lost in the reset | your answer 2026-11-16 | CANNOT VERIFY: from old report, not verified |
| 3MDAD | Test only | 35 / 15 drivers for the action classifier (seed 0) | AV1/DECISIONS D6 | OUTDATED |
| 5-fold CV | Not mentioned | 59 train+val drivers in 5 groups of 11–12; test drivers untouched | OVERNIGHT §8 addition 6 | MISSING FROM REPORT |
| IR-only split (2026-11-14) | — | Frozen driver-disjoint IR split. IR test has 20 drinking and 19 eating events (target was 30 + 30) | session 2026-11-14 | MISSING FROM REPORT |

## 6. Preprocessing, augmentation, label format

| Topic | What the report says | What the project has now | Source | Status |
|---|---|---|---|---|
| Frame sampling | 1 frame per 0.5 s in actions, 1.5 s in normal driving | `--every-pos 0.5`, `--every-neg 1.5` | `scripts/label_video_boxes.py` | STILL CORRECT |
| Stored size / train size | ≤ 960 px wide; 512 × 512 | Max side 960; det_v2d 512 | `label_video_boxes.py`, MODELS | STILL CORRECT |
| Roboflow filters | Boxes > 12 % (8 % drinks) removed | `ROBOFLOW_MAX_AREA = {0: 0.12, 1: 0.08, 2: 0.12}` | `scripts/build_det_v2.py` | STILL CORRECT |
| Hand occlusion | Real hand over 30–60 % of the phone | `rng.uniform(0.3, 0.6)` | `build_det_v2.py` | STILL CORRECT |
| Training augmentation | Mosaic, flip, zoom ±50 %, shift ±10 %, rotate ±5°, brightness ±40 % | `mosaic=1.0, fliplr=0.5, scale=0.5, translate=0.1, degrees=5.0, hsv_v=0.4` | `scripts/train.py` | STILL CORRECT |
| Auto-label teacher | YOLO26m at 1280 px + YOLO-World for food | `yolo26m.pt`, imgsz 1280; `yolov8l-worldv2.pt` for food | `configs/data.yaml` | STILL CORRECT |
| Label format | YOLO txt: class x y w h (0–1) | YOLO format via Ultralytics | DETV2, `build_det_v2.py` | STILL CORRECT |
| Action / phone crop preprocessing | — | Upper-body crop 2.5 × face size, 224 px gray, per-crop contrast stretch (1st–99th percentile); ear crops 1.2 face widths, 128 px; lap crop 2.5 × face size under the chin, 128 px; tiled face search for small faces | AV1/DECISIONS D8, D9, D16; MODELS v2 table | MISSING FROM REPORT |
| Face preprocessing | 640 × 480 at 30 fps; night gray → 3 ch + CLAHE; 3-frame median filter on EAR | Face runs at 640 × 480 @ 30 fps on the Pi; CLAHE in IR mode; blink uses a median-filtered openness signal (window size not checked) | FACE_EV, `models/face/src/dms_face/camera.py`, `blink.py` | STILL CORRECT |
| Hand check of 495 test frames | "Still to do" | Last written status (2026-10-17): needs the user. No later file says it was done | OVERNIGHT §5 | CANNOT VERIFY |

## 7. Models

| Topic | What the report says | What the project has now | Source | Status |
|---|---|---|---|---|
| Version 1 phone model | Ready image classifier trained on State Farm | `models/phone`: YOLOv8n-cls (Hugging Face Safe-Drive-TN), 10 → 3 classes, ONNX (2026-09-25). Kept, not deleted | `models/phone/docs/EVIDENCE.md` | STILL CORRECT |
| Release detector | YOLO26n (2.5 M weights), 512 px, gray | det_v2d: YOLO26n, 2.5 M params, 5.9 GFLOPs, 512 px | MODELS | STILL CORRECT |
| Model running on the Pi now | YOLO26n detector + rules | **v2 hybrid**: yolo26n-cls action model (224 px, INT8) + ear phone check + lap phone check (128 px, INT8). Box detector **off** (`--no-detect`), so there are **no drinking / eating alerts on the Pi**. Texting rule off (`--no-texting`) | `pi/start_stream.sh`, MODELS v2 section, `Subsystems/Distraction Subsystem.md` | OUTDATED |
| Why the Pi gives no drinking / eating alerts | — | In v2, drinking and eating come only from det_v2d boxes (D17), and the Pi starts with `--no-detect`. Recorded trade-offs: detector every frame ≈ 66 ms → 15.1 FPS worst case (D22, estimate); detector every 2nd frame ≈ +22 ms → ~20 FPS and its false phone alerts return (~79 /h on the IR test) (session 2026-10-26 08:35). The new drinking (IR-4) and eating models are on main as code only: the Pi was unreachable (IRR §5) and has no internet (your note); the stream still uses `--no-detect`, so the alerts stay off until it is changed; weights not on GitHub | `action_v1/DECISIONS.md` D17, D22; `pi/start_stream.sh`; sessions 2026-10-26, 2026-11-14 | MISSING FROM REPORT (must be stated in the new report) |
| Why we moved from det_v2d to the action classifier | — | 2026-10-25 live Pi test: near-ear calls missed. det_v2d phone score median 0.18 at the near ear vs 0.63 at the far ear; the alert rule fired 11 % vs 89 % of the time. An ear-zone rule raised SynDD right-ear calls 80 % → 90 % at 3.4 false alarms /h. The action brief followed 12 minutes after a suggestion to train on 3MDAD (35 / 15 drivers) | session 2026-10-25 23:40–23:48, 2026-10-26 00:04–00:16 | MISSING FROM REPORT |
| Drinking model | Detector cup box at the mouth | Product drinking model **IR-4**: cup/bottle-vs-empty-hand crop model (yolo26n-cls 128) with 1,500 phone hard negatives and light camera simulation. Code on main (PR #10); weights in the git-ignored `_held_data/`, not on GitHub. **Not set up on the Pi** | IRR, IRL, HELD, `action_v1/.gitignore` | MISSING FROM REPORT |
| Eating | Weak | Box detector: 0 % (MODELS). Experimental temporal head (GRU on IR-3 features): IR test **13/19 (68 %) at 10.15 FA/h, "Does not meet"** the target; main error yawning. Not on the Pi | MODELS, IRR §2, IRL | OUTDATED |
| Rejected models / ideas | 8 ideas, none better | det_v2c, ideas A–G, additions 1–3; plus later: yolo26s-cls (D15), smoking class (D21) | OVERNIGHT, AV1/DECISIONS | MISSING FROM REPORT (later rejections) |

## 8. Metrics

| Topic | What the report says | What the project has now | Source | Status |
|---|---|---|---|---|
| Step 2 Open Images only | Phone found in 1–35 % of car frames | v1_416 / v1_512 on 10 SynDD test drivers: 0.9–34.5 % per frame | DETV2 results table | STILL CORRECT |
| Step 4 det_v2b | Phone at ear 72–92 % of frames | 71.5 % / 91.6 % | DETV2 | STILL CORRECT |
| Step 5 det_v2d | 80–100 % calls, 0–5 false alarms /h | Test: 80 % / 100 %, 0 /h; validation 5.2 /h | OVERNIGHT §2, MODELS | STILL CORRECT |
| Current best phone numbers | det_v2d only | v2 vs det_v2d (same clips): SynDD calls 37/39 vs 34/39, texting 18/41 vs 14/41, FA 0 vs 0; DAD FA 3.6 vs 79.2 /h | MODELS, AV1/REPORT_v2 | MISSING FROM REPORT |
| Current best drinking numbers | det_v2d 90 % | IR test (untrimmed): IR-4 **18/20 = 90 % at ≤ 1.6 FA/h** (SynDD 16/18 at 1.07 /h, DAD 2/2 at 1.58 /h), "Meets the target". Old detector 16/18 at 0 /h + 2/2 at 8.67 /h | IRR §2 | MISSING FROM REPORT |

## 9. Hardware and camera

| Topic | What the report says | What the project has now | Source | Status |
|---|---|---|---|---|
| Camera | Infrared, centre mirror, 1296 × 972 | IR NoIR 160° module on the Pi now, installed after 2026-10-10 (exact date not recorded); the OV5647 RGB camera was a temporary stand-in before that. Capture 1296 × 972, 640 × 480 view (2026-10-25). No fisheye calibration yet (`rectify.enabled: false`); image rotated 180° | your answer 2026-11-16, PI_TARGET, `configs/profiles/pi.yaml`, `pi/start_stream.sh`, session 2026-10-25 | STILL CORRECT (calibration missing from report) |
| Speed on the Pi | "About 10 frames per second on the Raspberry Pi" | det_v2d INT8 ~45 ms per frame on the Pi ("measured earlier", AV1/PROGRESS). MODELS: "Raspberry Pi 5 numbers: still to be measured with all models running". v2 stream ~30 FPS (camera limit), ~15 ms model time, partly estimated | AV1/PROGRESS, MODELS, session 2026-11-08 | OUTDATED |
| Hailo AI HAT | Not mentioned | ONNX ready for the Hailo compiler; compile not done | OVERNIGHT §8 addition 7, MODELS | MISSING FROM REPORT |
| Our own recordings | None yet (Task 7) | Still none from the Pi camera. Only the developer's S01 laptop webcam clip (test only) | DATA, session 2026-11-14 ("I need ... clips recorded with the Pi camera") | STILL CORRECT |

## Questions for me (from this comparison)

All earlier questions are answered (held-object merged as PR #10 on 2026-11-16). Still open:

1. **Hand check of the 495 test frames:** was it ever done?
