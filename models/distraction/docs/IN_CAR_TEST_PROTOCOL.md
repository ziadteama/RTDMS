# In-car test session protocol

One-time session, **test data only** (never trained on), with 2–3 volunteers other than the
developer, using the real rig: Pi 5 + 160° NoIR camera at the centre mirror. About 10 minutes of
recording per person (two ~6 min passes), ~25 minutes per person including setup.

## Before the session

- **Consent.** Each volunteer reads and signs a one-page consent note: what is recorded (video
  of the driver seat, no audio), why (testing a driver-monitoring prototype), where it is kept
  (one laptop/Pi, never uploaded, never in git), how long (until frames are extracted and the
  results are written up; raw video is then deleted with `scripts/purge_recordings.py`), and
  that they can withdraw and have their recording deleted at any time.
- **Car parked, engine off, handbrake on.** Nobody drives during the session. The "driver"
  mimes driving with hands on the wheel.
- **Rig check.** Camera calibrated (`configs/camera_fisheye.yaml`) and driver ROI set
  (`select_roi.py --preview` shows head, both ears, hands, lap and wheel rim). Recording mode is
  the runtime mode: 1296x972 full-FOV.
- **Props**, one set per pass: a phone (+ phone holder mounted), a plastic bottle, a can or
  takeaway cup, a snack (crisps / sandwich / banana), wipes.
- **Lighting.** Pass A in daylight. Pass B at dusk/night if possible (IR LEDs on), otherwise in
  a garage. Note the condition with `--lighting`.

## Recording

From a laptop, SSH into the Pi and run (the operator reads the printed prompts aloud):

```bash
python scripts/record.py --subject P01 --scenario car_passA --lighting day --guided car --no-display
python scripts/record.py --subject P01 --scenario car_passB --lighting night --guided car --no-display \
    --notes "sunglasses"
```

Pass B changes appearance: sunglasses or a hat (or both), and different props where possible.
Each pass follows `GUIDED_CAR` in `scripts/record.py` (360 s):

| s | Prompt | Label |
|---|---|---|
| 0–20 | sit normally, eyes on road (per-drive baseline) | normal |
| 20–35 | phone call, RIGHT ear | phone_right_ear |
| 45–60 | phone call, LEFT ear (the hidden, far ear in a LHD car) | phone_left_ear |
| 70–90 | texting, phone held low, looking at it | phone_in_hand |
| 100–115 | phone in the holder, tap + brief glance | negative |
| 125–140 / 150–165 | drink from bottle / from can or cup | drinking |
| 175–205 | eat a snack, chew normally | eating |
| 215–235 / 235–250 | talk out loud / sing | negatives (eating must not fire) |
| 260–275 | **left elbow on the door, hand resting on head/temple** | negative (lands in the far-ear zone) |
| 275–295 | scratch face, adjust glasses, hand on chin | negatives |
| 295–320 | quick mirror and speedometer glances | negatives |
| 320–340 | nod down-up ×3, turn left-right ×3, slowly | head-pose validation |
| 340–350 | passenger uses a phone (if a passenger is present) | negative |

Short "normal" gaps between behaviours are part of the script; the prompt timeline is saved in
the clip's `.json` and serves as the label track.

## Afterwards

1. Evaluate (no training on these clips):
   ```bash
   python scripts/eval_events.py ours --src data/recordings --json results_incar.json
   ```
   (`ours` reads every clip's prompt timeline; per-behaviour precision / recall / F1, false
   alarms per hour over the normal + negative time, time-to-alert.)
2. Pose check: in the nod/turn segment, pitch must rise when the head goes down and yaw must
   change sign left vs right (`run.py --video <clip> --per-frame-log` shows the values).
3. If frames are needed (e.g. for a test-only detector set): `extract_frames.py ours ...`, then
   `purge_recordings.py --delete` removes the raw videos whose frames were extracted.
4. Raw videos never leave the machine; nothing under `data/` is committed (`.gitignore`).
