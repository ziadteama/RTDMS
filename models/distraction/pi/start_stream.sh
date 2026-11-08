#!/usr/bin/env bash
# Face mesh (drawn on the view) + drowsiness / PERCLOS + v2 phone alerts (action classifier +
# ear / lap phone checks, scripts/hybrid.py), no box detector. Served on http://<pi>:8080.
# --rotate 180: the camera is mounted upside down. Old setup (det_v2d boxes + drowsiness): start_stream_v1.sh. Extra arguments go to stream.py.
# Runs from the git clone (models/distraction/pi/) or from the ~/rtdms copy layout (see README.md).
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HERE/../scripts/stream.py" ]; then DIST="$HERE/.."; FACE="$HERE/../../face"
else DIST="$HERE/distraction"; FACE="$HERE/face"; fi
cd "$DIST"
export PYTHONPATH="$DIST/src:$FACE/src"
exec "${RTDMS_PYTHON:-$HOME/rtdms/.venv/bin/python}" scripts/stream.py --profile pi --no-rectify --roi full --drowsiness --no-texting \
    --hybrid --no-detect --mesh --rotate 180 "$@"
