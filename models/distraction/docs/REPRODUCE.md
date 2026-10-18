# Reproduce everything: data → training → export → evaluation

You do **not** need this to run the system: the trained models ship in `models/`
([models/README.md](../models/README.md)). Follow this to rebuild them, retrain on new data, or
re-run the experiments in [OVERNIGHT_REPORT.md](OVERNIGHT_REPORT.md).

Needs: a PC with an NVIDIA GPU (8 GB was enough), ~250 GB free disk for the data root, Python 3.11.
All commands run from `models/distraction/`. `<root>` is the data root in `configs/data.yaml`
(default `D:/rtdms-data`; the experiment scripts also accept the `RTDMS_DATA` environment variable).

## 0. Environment

```bash
python -m venv ../../../venvs/rtdms-train                    # anywhere outside the repo
# activate it, then:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
pip install -e ".[train,mediapipe,ncnn,onnx,bench,dev]"
python scripts/fetch_models.py                               # hand_landmarker.task
```

The labelling teachers (`yolo26m.pt`, `yolov8l-worldv2.pt`, `sam2.1_b.pt`) are downloaded by
Ultralytics on first use.

## 1. Datasets

| Dataset | Role | How to get it | Where it goes |
|---|---|---|---|
| **SynDD** (AI City Challenge 2024 Track 3) | main training + test data (IR, mirror view) | request access on the AI City Challenge site; it is shared as a Google Drive folder. Set up an `rclone` remote called `gdrive` (scope `drive.readonly`), then `python scripts/fetch_syndd.py` (A1 rear view + labels, ~100 GB; reads only the needed parts of the zips) | `<root>/public/syndd/A1/user_id_*/` |
| SynDD extra (optional) | experiments only | `fetch_syndd.py --set A2` (15 unlabelled drivers); `--views dash,right --only-users …` (other cameras) | `<root>/public/syndd/A2/`, same A1 folders |
| **Open Images V7** | training | `python scripts/build_openimages.py` (balanced subset, max 4,000 images per class) | `<root>/openimages/` |
| **Roboflow DMS_Project v2**, **ADMS_FINAL_3 v1** | training | free Roboflow account → each Universe page → Download → YOLO format, unzip | `<root>/public/roboflow/dms_project/`, `.../adms_final_3/` |
| **EBDD** | training + test | request from the EBDD page (BUET); keep the zip password out of git: set `EBDD_ZIP_PASSWORD`, then `python -c "import os,zipfile; zipfile.ZipFile('EBDD_Video_Database.zip').extractall('x', pwd=os.environ['EBDD_ZIP_PASSWORD'].encode())"` | `<root>/raw/ebdd/x/EBDD_Video_Database/` |
| **3MDAD** | unseen test | `kaggle datasets download -d anouarbenkhalifa/3mdad-multimodal-driver-action-distraction` (front view `Day-RGB2`) | `<root>/raw/3mdad/front/Day-RGB2/RGB2/S*/AC*/` |
| **DAD** (TU Munich) | unseen real-IR test | `DAD.part01.rar` from the TUM DAD page (10.5 GB = 3 drivers; all 10 parts = 100 GB, academic licence), then extract only the IR frames: `tar -xf DAD.part01.rar --include "*front_IR*" --include "*top_IR*"` (Windows `tar.exe` / bsdtar reads RAR) | `<root>/raw/dad/x/DAD/Tester*/` |

The SynDD driver split is fixed in `configs/syndd_split.json` (49 train / 10 validation / 10 test).
Never tune anything on the test drivers.

## 2. Labels (boxes in video)

```bash
# SynDD: action times from the CSVs + boxes from the teacher, kept only when they match the action
python scripts/label_video_boxes.py syndd --src <root>/public/syndd/A1 \
    --split-file configs/syndd_split.json --out <root>/det_v2/syndd --workers 4
python scripts/label_video_boxes.py ebdd --src <root>/raw/ebdd/x --out <root>/det_v2/ebdd --workers 4
# check them by eye (contact sheets) and prepare the 495-frame hand check
python scripts/hand_check_sheets.py --src <root>/det_v2/syndd --split test --out <root>/runs/hand_check
```

## 3. Training set

```bash
# merged_a: without Roboflow (first stage)
python scripts/build_det_v2.py --out <root>/det_v2/merged_a \
    --yolo <root>/det_v2/syndd --yolo <root>/det_v2/ebdd
# merged_b: the final set (53,889 train images incl. gray and hand-occlusion copies)
python scripts/build_det_v2.py --out <root>/det_v2/merged_b \
    --yolo <root>/det_v2/syndd --yolo <root>/det_v2/ebdd \
    --roboflow <root>/public/roboflow/dms_project --roboflow <root>/public/roboflow/adms_final_3
```

## 4. Training (three stages, ~6 h on an RTX 4060 Laptop)

```bash
# det_v2a: COCO weights, 416 px (stopped after 7 epochs)
python scripts/train.py --data <root>/det_v2/merged_a/data.yaml --imgsz 416 --batch 64 \
    --epochs 40 --look color --name det_v2a_416
# det_v2b: full set, 416 px, 35 epochs
python scripts/train.py --data <root>/det_v2/merged_b/data.yaml --imgsz 416 --batch 64 \
    --epochs 35 --look color --weights <root>/runs/det_v2a_416/weights/last.pt --name det_v2b_416
# det_v2d (release): gray-only (IR look), 512 px, 15 epochs, low learning rate
python scripts/train.py --data <root>/det_v2/merged_b/data.yaml --imgsz 512 --batch 32 \
    --epochs 15 --look ir --lr0 0.002 --warmup-epochs 1 \
    --weights <root>/runs/det_v2b_416/weights/best.pt --name det_v2d_ir_512
```

If training runs out of GPU memory, lower `--batch` and set
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. On Windows, "paging file too small" (error
1455) means training and evaluation were run at the same time: run them one after the other.

## 5. Export

```bash
# NCNN FP32 (the default model)
python scripts/export_ncnn.py --weights <root>/runs/det_v2d_ir_512/weights/best.pt \
    --name det_v2d_ir_512 --imgsz 512
# INT8 mixed precision for the Pi (ncnn command-line tools from github.com/Tencent/ncnn/releases)
python scripts/quantize_int8.py --tools <ncnn>/bin --images "<root>/det_v2/syndd/images/train/*.jpg"
# ONNX for onnxruntime / the Hailo-8 compiler
python -c "from ultralytics import YOLO; YOLO('<root>/runs/det_v2d_ir_512/weights/best.pt').export(format='onnx', imgsz=512, opset=11, simplify=True)"
# pose model for the texting rule
python scripts/export_ncnn.py --weights models/yolo26n-pose.pt --name yolo26n_pose_320 --imgsz 320
# check that NCNN gives the same boxes as PyTorch
python scripts/check_detector_parity.py --images some.jpg --pt <root>/runs/det_v2d_ir_512/weights/best.pt
```

`quantize_int8.py` rebuilds the shipped INT8 model: on 600 validation frames the rebuilt and the
shipped one agree within noise (phone P 0.796 / 0.804, R 0.612 / 0.616; drink identical).

## 6. Evaluation (alert level, like the live system)

```bash
# 1) choose thresholds on the VALIDATION drivers
python scripts/eval_simple.py --split val --models det_v2d=models/det_v2d_ir_512.pt@512 \
    --conf 0.25 --out <root>/runs/eval_val
python experiments/sweep_model.py val det_v2d models/det_v2d_ir_512.pt 512 0.35,0.40,0.45 0.45,0.50
# 2) score the TEST drivers once with the chosen thresholds
python scripts/eval_simple.py --split test --models det_v2d=models/det_v2d_ir_512.pt@512 \
    --class-conf phone=0.40,drink=0.45,food=0.40 --out <root>/runs/eval_test
```

`eval_simple.py` replays every SynDD video at 10 frames per second through the live geometry and
rules, and reports per behaviour: share of actions caught, false alarms per hour of non-phone
driving, time to alert, and 5–95 % ranges from re-sampling the drivers. Face and detector passes
are cached under `<root>/eval_cache/` (keyed by the weights file, so a retrained model never reuses
old detections).

Experiments (unseen datasets, cross-validation, rule tuning, …): [../experiments/README.md](../experiments/README.md).

## 7. Testing on your own camera

Record volunteers with [IN_CAR_TEST_PROTOCOL.md](IN_CAR_TEST_PROTOCOL.md) (`scripts/record.py`
saves the prompt times as labels) and score the clips with `scripts/eval_events.py ours`. Add their
normal-driving frames to training as "no object" examples: that is the most effective way to cut
false alarms on a new camera.
