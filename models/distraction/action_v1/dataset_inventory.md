# Dataset inventory — D:\ (2026-11-14, read-only scan)

Method:
- **Scan:** all of `D:\` outside game/system folders, folders listed and sized; archives > 20 MB
  found by name (only 4 exist). The DAD RAR4 volume was listed with a read-only header walker
  (`src/rar4_list.py`, no extraction).
- **Modality:** measured on sampled frames (`src/inventory_probe.py`), not taken from folder
  names. Colour = mean |R−G|+|G−B|; ≈ 0 means grey/IR, 15–50 means real RGB. Contact sheet:
  `_held_data/ir/inventory_sheet.jpg`.
- **Drinking etc.:** whether the dataset's own label list contains those classes.

| Dataset | Path (D:\) | Size | State | Modality (measured) | Views | fps / res | Drivers | Classes (drink / eat / phone / smoke / yawn / hand-face) | Annotation | Used now? |
|---|---|---|---|---|---|---|---|---|---|---|
| SynDD (AI City 2023/24, A1) | rtdms-data\public\syndd\A1 | 166 GB (A1+A2) | extracted MP4 | **grey, colour 0.1 = monochrome / NIR-sensitive** (daylight, not active IR) | rear view (mirror), dashboard, right window | 30 fps, 1920×1080 | 69 | ✔ / ✔ / ✔ / ✘ / ✔ / ✔ (hand on head) + talking, singing, reaching, control panel, hair & makeup, pick-up | time-stamped segments (start/end) | **rear view only** |
| SynDD A2 | rtdms-data\public\syndd\A2 | (in above) | extracted MP4 | grey (0.1) | rear view | 30 fps, 1920×1080 | 10 | (same class set) | **labels not released** (2024 test set; label zip has A1 only) | no |
| 3MDAD Day-RGB2 front | rtdms-data\raw\3mdad\front\Day-RGB2 | 3.9 GB | extracted JPG | **RGB** (colour 16–25) | front | ~3 fps frames, 640×480 | 50 | ✔ / ✘ / ✔ / ✔ / fatigue (AC12) / hair & makeup | clip label (folder per action) | yes (RGB→grey) |
| DAD (Driver Anomaly Detection) | rtdms-data\raw\dad\x\DAD + archive\DAD.part01.rar | 18 GB | **part 1 only**, extracted | **IR** (colour 0) front_IR + top_IR | front, top | 45 fps, 224×171 | **3 local** (Tester1, 10, 11) of ~31 | ✔ / ✘ / ✔ (talk L/R, messaging L/R) / ✘ / ✘ / ✘ | clip label (folder per action) | yes, front_IR test only |
| EBDD | rtdms-data\raw\ebdd | 2.0 GB | zip + extracted MP4 | **RGB** (colour 15–24) | side | 30 fps, 854×480 | 13 | ✘ / ✔ / ✔ / ✘ / ✘ / ✘ (+ attentive / unattentive) | video label | yes (RGB→grey) |
| Drive&Act (videos only) | Data Sets\inner_mirror, Data Sets\steering_wheel | 2.1 + 2.7 GB | extracted MP4 | **NIR** (colour 0) | inner mirror, steering wheel | 30 fps, 1280×1024 | 15 (vp1–vp15), 30 videos/view | ✔ / ✔ / ✔ / ✘ / ✘ / ✔ (in the dataset) | **annotation files missing** (only calibration + timestamps on disk) | no |
| AUC Distracted Driver v1 / v2 | Data Sets\v1_cam1_no_split, Data Sets\v2_cam1_cam2_ split_by_driver | 1.3 + 1.2 GB | extracted JPG | **RGB** (colour 12–48) | side (cam1, cam2) | images, 1920×1080 / 640×480 | v2: ~44 | ✔ (drink) / ✘ / ✔ / ✘ / ✘ / ✔ (hair & makeup) | image label | no (models/phone uses State Farm weights) |
| UTA-RLDD Fold3 part 2 | Data Sets\Fold3_part2 | 7.6 GB | extracted MP4 | RGB | front (phone) | 25 fps, 720×1280 | 6 (31–36) | drowsiness levels only | video label | no (not relevant) |
| MRL Eye | Data Sets\data (train/val awake/sleepy) | 383 MB | extracted PNG | IR (colour 0) | eye crops | 69×69 | — | eye open / closed | image label | no (face model area) |
| p022 (depth + 2 IR, one participant) | Data Sets\p022 | 7.0 GB | extracted BMP | IR + depth | front | 320×240 | 1 | gaze-type labels (`*_local.txt`) | per frame | no (not relevant) |
| WESAD | Data Sets\WESAD | — | — | physiology | — | — | 15 | — | — | physiology subsystem |
| Roboflow exports | rtdms-data\public\roboflow (adms_final_3, dms_project) | 1.7 GB | extracted | mixed | — | — | — | detector boxes | boxes | release detector training |

**IR / NIR sources with drinking or eating labels on this disk:**
- **SynDD** (monochrome, 69 drivers, drinking + eating, time-stamped).
- **DAD** (true IR, 3 drivers, drinking only).

Drive&Act is IR and has the right classes, but its labels are missing.

## Have but not used yet

| What | What it would add |
|---|---|
| **SynDD A1 dashboard + right-window views** (same 69 drivers, same labels) | 2 more camera positions per event: viewpoint robustness for training. Not new drivers, so it can't enlarge the test set. |
| **Drive&Act NIR videos** (15 drivers × 2 NIR views) | The best match for our camera (NIR, in-car, mirror-like view, night-style lighting), with eating + drinking + phone + more. **Needs the annotation files.** |
| **AUC v1/v2** | ~44 more drivers with drinking (RGB side view; usable only as RGB→IR-like training data, image-level labels, no hand-mouth timing). |
| **SynDD A2** (10 drivers) | Unlabelled; only usable for self-training. |
| **DAD top_IR** (same 3 drivers) | Second IR view of the same test events. |

## Missing (truly absent from D:)

| Dataset | What it would add | Request page | What you must do |
|---|---|---|---|
| **DAD parts 2…N** | The remaining ~28 IR drivers (the DAD training set), with drinking. Only `DAD.part01.rar` (Tester1, 10, 11) is on disk. | github.com/okankop/Driver-Anomaly-Detection (download links in the README) | Download the remaining `DAD.partNN.rar` volumes into `D:\rtdms-data\raw\dad\archive\` and extract them (needs 7-Zip or WinRAR). |
| **Drive&Act annotations** | Labels for the NIR videos already on disk (activities incl. eating, drinking). | driveandact.com | Fill in the registration / licence form; download the activity annotation CSVs (fine-grained "activities", 3 s chunks) and put them next to `Data Sets\inner_mirror`. |
| **DMD (incl. IR)** | Large IR + RGB driver set (37 drivers) with drinking, phone, hair/makeup and more; the face camera is close to our setup. | dmd.vicomtech.org | Request access with the form on the site; download the distraction subset ("dmd/dtrans" IR + body/face cameras). |
| **3MDAD night (IR) + side view** | IR versions of the same 50 drivers (drinking, phone, smoking, fatigue). Only Day-RGB2 front is on disk. | 3MDAD authors' page (Ben Khalifa et al., "3MDAD"); the dataset is given on request by email | Email the authors with the licence / agreement they ask for; download Night-IR front and side. |
| **100-Driver** | 100 drivers, 4 cameras incl. NIR, day and night, 22 classes incl. drinking and eating. | 100-driver.github.io | Fill in the request form on the site; download the NIR subsets. |
| **State Farm** | 22k RGB images, 10 classes (drink, phone, texting, hair). | kaggle.com/c/state-farm-distracted-driver-detection | Kaggle account, accept the competition rules, download. |

I submitted no forms and sent no emails (as instructed).
