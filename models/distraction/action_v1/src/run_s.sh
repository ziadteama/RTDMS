#!/usr/bin/env bash
# Step 4 extra: the "s" size action classifier, after the phone classifier is done.
cd /d/rtdms-data/action_v1/src
PY=/c/Users/youss/venvs/rtdms-train/Scripts/python.exe
until grep -q "=== phone finished" ../runs/train_phone_n128.log; do sleep 30; done
for try in 1 2 3; do
  echo "=== act_s try $try $(date +%T)" >> ../runs/train_act_s224.log
  $PY train_cls.py D:/rtdms-data/action_v1/data/cls act_s224 yolo26s-cls.pt 224 30 128 >> ../runs/train_act_s224.log 2>&1
  tr '\r' '\n' < ../runs/train_act_s224.log | grep -q "Results saved" && break
done
echo "=== act_s finished $(date +%T)" >> ../runs/train_act_s224.log
