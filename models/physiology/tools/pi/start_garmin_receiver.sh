#!/usr/bin/env bash
# Start (or restart) the Garmin RR receiver on the Pi, with the live page on port 8081.
#
#   bash tools/pi/start_garmin_receiver.sh
#
# Layout it expects (as deployed on the RTDMS Pi):
#   ~/dms/venv            Python venv with the physiology package deps + `garmin` extra (bless)
#   ~/dms/garmin/src      copy of models/physiology/src (only when not run from the git clone)
#   ~/dms/garmin/logs     raw CSV logs, one file per start
# Run tools/pi/setup_bluetooth_le.sh once first (LE-only controller, fast advertising).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$HERE/../../src/dms_physiology" ]; then SRC="$(cd "$HERE/../../src" && pwd)"  # git clone
else SRC="$HOME/dms/garmin/src"; fi
mkdir -p ~/dms/garmin
cd ~/dms/garmin
mkdir -p logs
# The watch only reports advertisements that carry the "discoverable" flags; BlueZ adds them only
# while the adapter is discoverable. Without this the watch scans forever.
bluetoothctl discoverable-timeout 0 > /dev/null
bluetoothctl discoverable on > /dev/null
pkill -f '[d]ms_physiology.garmin_receiver' || true
sleep 1
export PYTHONPATH="$SRC" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
nohup ~/dms/venv/bin/python -u -m dms_physiology.garmin_receiver --quiet --http 8081 \
    --csv "$HOME/dms/garmin/logs/garmin_rr_$(date +%Y%m%d_%H%M%S).csv" \
    > ~/dms/garmin/receiver.log 2>&1 < /dev/null &
sleep 4
# A watch still connected from before the restart keeps writing to the OLD server's handles and
# nothing arrives. Drop such links now that the new server is up; the watch reconnects and
# looks the RR characteristic up again.
for d in $(bluetoothctl devices Connected | awk '{print $2}'); do
  bluetoothctl disconnect "$d" > /dev/null
done
cat ~/dms/garmin/receiver.log
pgrep -af '[d]ms_physiology.garmin_receiver' | head -1
