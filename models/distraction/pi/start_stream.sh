#!/usr/bin/env bash
# Face mesh (drawn on the view) + drowsiness / PERCLOS + v2 phone alerts (action classifier +
# ear / lap phone checks, scripts/hybrid.py), no box detector. Served on http://<pi>:8080.
# --rotate 180: the camera is mounted upside down. Old setup (det_v2d boxes + drowsiness): start_stream_v1.sh. Extra arguments go to stream.py.
cd "$(dirname "$0")/distraction"
export PYTHONPATH="$PWD/src:$PWD/../face/src"
exec ../.venv/bin/python scripts/stream.py --no-rectify --roi full --drowsiness --no-texting \
    --hybrid --no-detect --mesh --rotate 180 "$@"
