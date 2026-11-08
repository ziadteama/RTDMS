#!/usr/bin/env bash
# v2: re-runs step 2 for every dataset to add the lap crop; CSVs in data/v2. Log: runs/extract_v2.log
cd /d/rtdms-data/action_v1/src
PY=/c/Users/youss/venvs/rtdms-train/Scripts/python.exe
for ds in 3mdad ebdd dad syndd syndd_fish; do
  if [ -f ../data/v2/$ds.csv ]; then echo "$ds already done"; continue; fi
  for try in 1 2 3; do
    echo "=== $ds try $try $(date +%T)"
    $PY extract.py $ds 12 2>&1 | grep --line-buffered -v "^W0000\|^I0000\|inference_feedback\|WARNING: All log"
    [ -f ../data/v2/$ds.csv ] && break
  done
  df -h /d | tail -1
done
echo "=== all done $(date +%T)"
