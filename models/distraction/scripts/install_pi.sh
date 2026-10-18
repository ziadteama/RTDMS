#!/usr/bin/env bash
#
# Raspberry Pi 5 setup for the distraction module (Raspberry Pi OS, aarch64).
#
#   cd models/distraction && bash scripts/install_pi.sh
#
# Installs only RUNTIME pieces: MediaPipe (face mesh + hands) and the ncnn wheel (detector).
# No PyTorch / Ultralytics on the Pi: the trained NCNN models ship in git (models/README.md);
# new ones are exported on the PC (scripts/export_ncnn.py, scripts/quantize_int8.py).
#
# Wheel availability (checked 2026-10-10 on PyPI):
#   mediapipe 1.1.0  py3-none-manylinux_2_28_aarch64  -> any Python 3, glibc >= 2.28
#                                                       (Bookworm 2.36, Trixie 2.41: OK)
#   ncnn 1.0.20260526 cp310..cp314 manylinux aarch64  -> Pi OS Python 3.11 / 3.13: OK
# If a future Pi OS Python has no mediapipe wheel: set facemesh.backend: dms_face with
# dms_face_backend: litert (ai-edge-litert has cp310-cp314 aarch64 wheels) and hands.source: off
# (or detector, once the fine-tuned model has a hand class).

set -euo pipefail
say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m    %s\033[0m\n' "$1"; }

cd "$(dirname "$0")/.."

say "Machine"
echo "    arch   : $(uname -m)"
[ -r /proc/device-tree/model ] && echo "    board  : $(tr -d '\0' < /proc/device-tree/model)"
echo "    python : $(python3 --version)"
echo "    glibc  : $(ldd --version | head -1)"

say "System packages (picamera2 comes from apt, not pip)"
if ! python3 -c "import picamera2" 2>/dev/null; then
    sudo apt update && sudo apt install -y python3-venv python3-picamera2
else
    echo "    picamera2 already importable"
fi

say "Virtual environment (--system-site-packages so picamera2 is visible)"
[ -d .venv ] || python3 -m venv --system-site-packages .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[mediapipe,ncnn,bench,dev]"

say "Model assets"
python scripts/fetch_models.py
for m in det_v2d_ir_512_ncnn_model det_v2d_ir_512_det_aciq_mixed_ncnn_model yolo26n_pose_320_ncnn_model; do
    if [ -f "models/$m/model.ncnn.param" ]; then
        echo "    have models/$m"
    else
        warn "missing models/$m: it ships in git, run 'git pull' (or copy it from the PC)"
    fi
done

say "Verify"
python - <<'PY'
import importlib
for m in ("numpy", "cv2", "yaml", "mediapipe", "ncnn", "picamera2"):
    try:
        mod = importlib.import_module(m)
        print(f"    {m:10s} {getattr(mod, '__version__', 'ok')}")
    except Exception as e:  # report every missing piece, not just the first
        print(f"    {m:10s} MISSING ({e})")
PY
python -m pytest -q
echo
echo "Next: python scripts/calibrate_fisheye.py --headless ...   (see README)"
