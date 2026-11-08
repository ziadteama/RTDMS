#!/usr/bin/env bash
# Phone classifier after the action model (two trainings at once ran out of Windows commit memory).
cd /d/rtdms-data/action_v1/src
PY=/c/Users/youss/venvs/rtdms-train/Scripts/python.exe
until tr '\r' '\n' < ../runs/train_act_n224.log | grep -q "Results saved\|Traceback"; do sleep 30; done
for try in 1 2 3; do
  echo "=== phone try $try $(date +%T)" >> ../runs/train_phone_n128.log
  $PY train_cls.py D:/rtdms-data/action_v1/data/phone phone_n128 yolo26n-cls.pt 128 25 256 >> ../runs/train_phone_n128.log 2>&1
  tr '\r' '\n' < ../runs/train_phone_n128.log | grep -q "Results saved" && break
done
echo "=== phone finished $(date +%T)" >> ../runs/train_phone_n128.log
