#!/usr/bin/env bash
# Open Images -> teacher labels -> our-camera conversion -> dataset -> train 416 + 512 -> export
# -> evaluation. Run after scripts/build_openimages.py. TRAINING ENV.
#
#   PY=/path/to/venv/python bash scripts/run_oiv_pipeline.sh [dataset_name]
#
# Add YawDD / SynDD later by extracting + teacher-labelling + converting them, then
# re-running only the build_dataset / train steps with --background / --drivers.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}
NAME=${1:-v1}
DATA=$($PY -c "import yaml;print(yaml.safe_load(open('configs/data.yaml'))['root'])")
OIV="$DATA/openimages"
CONV="$DATA/converted/oiv"
step() { printf '\n==== %s  %s\n' "$(date +%H:%M:%S)" "$1"; }

for split in train val test; do
  if [ ! -f "$OIV/labels_meta/${split}_teacher_summary.json" ]; then
    step "teacher labels: $split"
    $PY scripts/teacher_label.py --images "$OIV/images/$split" --gt "$OIV/labels_gt/$split" \
        --out "$OIV/labels/$split"
  fi
done

for split in train val test; do
  if [ ! -d "$CONV/images/$split" ]; then
    step "convert to our camera: $split"
    $PY scripts/domain_convert.py --src "$OIV" --split "$split" --out "$CONV" \
        --faces "$OIV/meta/${split}_faces.json" --variants 1 --hand-bank-from "$OIV"
  fi
done

step "assemble dataset $NAME"
$PY scripts/build_dataset.py --name "$NAME" --fixed "$CONV"

for sz in 416 512; do
  if [ ! -f "$DATA/runs/${NAME}_${sz}/weights/best.pt" ]; then
    step "train imgsz $sz"
    $PY scripts/train.py --data "$DATA/datasets/$NAME/data.yaml" --imgsz "$sz" \
        --name "${NAME}_${sz}"
  fi
  step "export NCNN imgsz $sz"
  $PY scripts/export_ncnn.py --weights "$DATA/runs/${NAME}_${sz}/weights/best.pt" \
      --name "${NAME}_${sz}" --imgsz "$sz"
done

step "evaluate on Open Images test (converted, gray): each model at its own size"
$PY scripts/eval_detector.py --list "$DATA/datasets/$NAME/test.txt" \
    --models models/yolo26n.pt "$DATA/runs/${NAME}_416/weights/best.pt" --imgsz 416 \
    --json "$DATA/datasets/$NAME/eval_oiv_test_416.json"
$PY scripts/eval_detector.py --list "$DATA/datasets/$NAME/test.txt" \
    --models models/yolo26n.pt "$DATA/runs/${NAME}_512/weights/best.pt" --imgsz 512 \
    --json "$DATA/datasets/$NAME/eval_oiv_test_512.json"

S01=$(ls data/recordings/S01_guided_*.mp4 2>/dev/null | grep -v overlay | head -1 || true)
if [ -n "$S01" ]; then
  step "S01 (test only, never trained on): detector diagnostic + event-level"
  $PY scripts/diagnose_detector.py "$S01" --imgsz 416,512 --confs 0.25 \
      --models "yolo26n,$DATA/runs/${NAME}_416/weights/best.pt,$DATA/runs/${NAME}_512/weights/best.pt" \
      --json "$DATA/datasets/$NAME/diag_S01.json"
  for sz in 416 512; do
    $PY scripts/eval_events.py s01 --src "$S01" --weights "models/${NAME}_${sz}_ncnn_model" \
        --imgsz "$sz" --hands detector \
        --json "$DATA/datasets/$NAME/events_S01_${sz}.json"
  done
fi
step "done"
