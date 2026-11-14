#!/usr/bin/env bash
# Build the INT8 held cup model ON THE PI (the ncnn2table tool is blocked by Windows Application
# Control on the dev PC). WRITTEN OFFLINE 2026-11-14, NOT YET RUN.
#
#   bash build_int8_on_pi.sh <fp32 ncnn model dir> <calibration crops dir (jpg, recursive)>
#
# Same steps as action_v1/src/bench.py int8(): ncnnoptimize -> ncnn2table (KL, 600 crops,
# /255 RGB input like Ultralytics) -> ncnn2int8. Builds the ncnn tools once (pinned tag).
set -euo pipefail
FP32="${1:?fp32 ncnn model dir}"
CALIB="${2:?calibration crop dir}"
NCNN_TAG="${NCNN_TAG:-20240820}"
TOOLS="${NCNN_TOOLS:-$HOME/ncnn-tools}"
OUT="${FP32%_ncnn_model}_int8kl_ncnn_model"

if [ ! -x "$TOOLS/ncnn2table" ]; then
  echo "[int8] building ncnn tools $NCNN_TAG into $TOOLS (one time, ~20 min on a Pi 5)"
  sudo apt-get install -y cmake g++ libprotobuf-dev protobuf-compiler libopencv-dev >/dev/null
  SRC="$(mktemp -d)/ncnn"
  git clone --depth 1 --branch "$NCNN_TAG" https://github.com/Tencent/ncnn.git "$SRC"
  cmake -S "$SRC" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release -DNCNN_BUILD_TOOLS=ON \
        -DNCNN_BUILD_EXAMPLES=OFF -DNCNN_BUILD_BENCHMARK=OFF -DNCNN_VULKAN=OFF >/dev/null
  cmake --build "$SRC/build" -j4 >/dev/null
  mkdir -p "$TOOLS"
  cp "$SRC/build/tools/ncnnoptimize" "$SRC/build/tools/quantize/ncnn2table" \
     "$SRC/build/tools/quantize/ncnn2int8" "$TOOLS/"
fi

WORK="$(mktemp -d)"
find "$CALIB" -name '*.jpg' | shuf --random-source=<(yes) | head -n 600 > "$WORK/calib.txt"
echo "[int8] $(wc -l < "$WORK/calib.txt") calibration crops"
"$TOOLS/ncnnoptimize" "$FP32/model.ncnn.param" "$FP32/model.ncnn.bin" \
  "$WORK/opt.param" "$WORK/opt.bin" 0
"$TOOLS/ncnn2table" "$WORK/opt.param" "$WORK/opt.bin" "$WORK/calib.txt" "$WORK/t.table" \
  mean=[0,0,0] norm=[0.003922,0.003922,0.003922] shape=[128,128,3] pixel=RGB thread=4 method=kl
mkdir -p "$OUT"
"$TOOLS/ncnn2int8" "$WORK/opt.param" "$WORK/opt.bin" "$OUT/model.ncnn.param" \
  "$OUT/model.ncnn.bin" "$WORK/t.table"
cp "$FP32/metadata.yaml" "$OUT/"
echo "[int8] wrote $OUT"
