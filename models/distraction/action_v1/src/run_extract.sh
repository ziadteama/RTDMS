#!/usr/bin/env bash
# Runs step 2 for every dataset, one after another; log in runs/extract.log
cd /d/rtdms-data/action_v1/src
PY=/c/Users/youss/venvs/rtdms-train/Scripts/python.exe
for ds in syndd 3mdad ebdd dad syndd_fish; do
  if [ -f ../data/$ds.csv ]; then echo "$ds already done"; continue; fi
  for try in 1 2 3; do
    echo "=== $ds try $try $(date +%T)"
    $PY extract.py $ds 16 2>&1 | grep -v "^W0000\|^I0000\|inference_feedback\|WARNING: All log" && [ -f ../data/$ds.csv ] && break
  done
  df -h /d | tail -1
done
echo "=== all done $(date +%T)"
