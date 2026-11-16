#!/usr/bin/env bash
# ONE COMMAND for the full Pi held-object evaluation, once the Pi is reachable.
# WRITTEN OFFLINE 2026-11-14, NOT YET RUN ON THE PI.
#
# On the Pi, from the git clone (branch with this folder checked out):
#   bash models/distraction/action_v1/pi_held/run_pi_eval.sh ~/rtdms_rec
#
# ~/rtdms_rec = the recorded test set (RECORDING_CHECKLIST.md): *.mp4 + labels.csv (file,label).
# Steps: INT8 build (once) -> IR-frame results + FPS with phone model and face mesh running ->
# wrist check sheet. Results in ~/rtdms_held_eval/ (report.json, wrist_check.jpg).
# Stop pi/start_stream.sh first, so the numbers are not shared with a second pipeline.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REC="${1:?recorded clips dir with labels.csv}"
PY="${RTDMS_PYTHON:-$HOME/rtdms/.venv/bin/python}"
ONNX="$HERE/models/held_cup_nano.onnx"
FP32="$HERE/models/held_cup_nano_ncnn_model"
INT8="$HERE/models/held_cup_nano_int8kl_ncnn_model"
CALIB="$HERE/calib"

if [ ! -d "$INT8" ]; then
  bash "$HERE/build_int8_on_pi.sh" "$ONNX" "$CALIB"   # also writes the FP32 NCNN dir
fi
for M in "$INT8" "$FP32"; do
  echo "== $(basename "$M")"
  "$PY" "$HERE/pi_held_eval.py" --clips "$REC" --model "$M" \
        --out "$HOME/rtdms_held_eval/$(basename "$M")"
done
echo "Live camera, 60 s, INT8 (FPS on the real sensor):"
"$PY" "$HERE/pi_held_eval.py" --seconds 60 --model "$INT8" --out "$HOME/rtdms_held_eval/live"
