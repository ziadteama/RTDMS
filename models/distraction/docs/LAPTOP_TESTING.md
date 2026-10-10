# Live testing on a laptop webcam

Until the Pi camera arrives, `scripts/live.py` runs the full pipeline (detector, face mesh,
rules, smoothing) on a Windows laptop webcam, with an overlay and live controls.

## Run

```bash
cd models/distraction
python scripts/live.py --profile laptop_webcam              # free play
python scripts/live.py --profile laptop_webcam --guided     # ~2 min scored prompt sequence
python scripts/live.py --profile laptop_webcam --fps-cap 10 # behave like the Pi's frame rate
```

Open the webcam's privacy shutter first. A covered lens gives a near-black image and simply no
face (seen on 2026-10-11: mean brightness 14/255).

**Startup side check (5 s):** touch your RIGHT ear with your RIGHT hand. If your hand lands on
the mesh's left-ear point (454) the image is mirrored and the flip is turned on automatically;
the console says which. Skip it with `--no-side-check`.

**Keys**

| key | action |
|---|---|
| q / Esc | quit |
| r | restart the head-pose baseline (sit normally ~10 s) |
| g | grayscale on/off (on = what the IR camera will give) |
| m | next detector: stock yolo26n → v1_416 → v1_512 → any other `models/*_ncnn_model` |
| [ / ] | detector confidence −/+ 0.05 (all classes) |
| d | debug overlay on/off (mesh, zones, reasons, per-stage ms) |

Every change is printed as one line, e.g.
`[live] model switched: model=v1_416 (..., imgsz 416, hands detector) conf=0.10 gray=True flip=False fps_cap=None`
— copy those lines when reporting what worked.

**Guided mode** prompts, in order: normal (baseline) · phone right ear · phone left ear · phone
held low · drinking · eating · talking · hand on face · elbow on the desk with the hand on your
head, with short normal gaps between them. Have a phone, a cup or bottle and a snack ready. At
the end it writes `reports/live_<utc>.md` and `.json`:

| column | meaning |
|---|---|
| hit rate | share of the segment's frames with the expected behaviour active (after smoothing) |
| raw rate | share of frames where the rules' per-frame evidence fired (before smoothing): did the detector + geometry see it at all |
| alerts | behaviour onsets in the segment |
| false alarms | onsets of anything that was not the prompted behaviour (in negative and normal segments every onset is one) |
| time-to-alert | seconds from the prompt to the expected behaviour becoming active |

Model / threshold changes during a guided run are recorded per segment (`models` column in the
JSON), so you can compare settings in one sitting.

**Privacy:** by default only the event log (`logs/live_*.jsonl`, behaviour start/end lines) and
the guided summary are written. `--save` additionally writes the raw video and a sidecar to
`data/recordings/` so the run can be replayed (`eval_events.py ours --src data/recordings`).
All of these are gitignored.

## Position the laptop like the mirror camera

The real camera sits at the centre rear-view mirror: above eye level, in front, and to the
driver's right (left-hand-drive car), looking down and across at the driver.

- Raise the laptop so the webcam is ~10–20 cm above your eyes (books under it), tilted down.
- Sit off-centre: the webcam should be ahead and to your **right**, ~30–40° off your straight
  ahead, so your right cheek faces it more than your left. That makes your left ear the
  "far", partly hidden ear, as in the car.
- Distance ~60–80 cm. Keep your hands, a "steering wheel" height and your lap in frame.
- Optionally narrow the ROI to you: `python scripts/select_roi.py --profile laptop_webcam`
  (saves `roi.rect` into the profile).

## What webcam results can and cannot tell us

**Can:** whether the rules and smoothing behave sensibly end to end; whether a given detector
sees a phone / cup / food in a real hand at all; how the left/right ear logic, the far-ear
hand-only rule, chewing vs talking and the head-down escalation feel live; rough relative
comparisons between models and thresholds on the same person and setup.

**Cannot:**

- *Accuracy for the car.* One person, one room, colour optics (even in grayscale mode), no IR
  illumination, no fisheye: the camera domain is different, exactly the gap that made the Open
  Images fine-tune look good offline and poor on S01.
- *Speed on the Pi.* The laptop CPU is several times faster; `--fps-cap` only reproduces the
  Pi's frame RATE for the smoothing, not its per-stage cost. Pi numbers come from
  `scripts/bench.py` on the Pi.
- *False-alarm rates.* A few minutes at a desk is not driving. Use YawDD and the in-car session.
- *Fisheye / ROI behaviour.* Rectification is off here.

Treat a webcam result as "works / doesn't work and why", not as a number for the report.
