# Live testing on a laptop webcam

> **Current target (2026-10-11): laptop webcam, colour, daylight / indoor lighting only.**
> The IR Pi camera is parked. Fisheye rectification is off, inference and training are in
> colour, and the IR look / fisheye augmentations are off (`configs/data.yaml: look: color`).
> Grayscale and the IR settings remain config switches (`capture.grayscale`, `look: ir`) to go
> back later without code changes.

`scripts/live.py` runs the full pipeline (detector, face mesh, MediaPipe hands, YOLO26n-pose,
ear-crop classifier when trained, rules, smoothing) on the webcam with an overlay and live
controls.

## Run

```bash
cd models/distraction
python scripts/live.py --profile laptop_webcam              # free play
python scripts/live.py --profile laptop_webcam --guided     # ~2.5 min scored prompt sequence
python scripts/live.py --profile laptop_webcam --fps-cap 10 # Pi-like frame rate for smoothing
```

Open the webcam's privacy shutter first (a covered lens gives a near-black image and no face).

**Startup side check (5 s):** touch your RIGHT ear with your RIGHT hand. If your hand lands on
the mesh's left-ear point (454) the image is mirrored and the flip is turned on automatically;
the console says which. Skip it with `--no-side-check`.

**Keys**

| key | action |
|---|---|
| q / Esc | quit |
| r | restart the head-pose baseline (sit normally ~10 s) |
| g | grayscale on/off (default off: colour is the target) |
| m | next detector: stock yolo26n → v1_416 → v1_512 → any other detector in `models/` |
| [ / ] | detector confidence −/+ 0.05 (all classes) |
| d | debug overlay on/off (mesh, zones, pose wrists, reasons, per-stage ms) |
| p | pose wrist evidence on/off |
| c | ear-crop classifier on/off (once trained) |

Every change prints one line with model, threshold, grayscale, flip, FPS cap and the active
**ear setup** (`hands`, `hands+pose`, `hands+pose+clf`) — copy those lines when reporting.

## Phone at the ear

The detector rarely sees a phone held at an ear (hand and head hide it), so a call is also
recognised from the hand:

- **WARNING:** a hand held at either ear for ≥ 3 s (`rules.yaml: hand_at_ear.dwell_s`).
  Short detection misses (< 0.7 s) don't end the episode; scratching (< 3 s) should not fire.
- **ALERT:** during that episode a phone box appears in the ear zone, or the ear-crop
  classifier's smoothed P(phone) ≥ 0.6. A phone box at the ear on its own is also an ALERT.
- **Ear zone** = beside the ear, from the eye line to the jaw line. A hand above the eye line
  (temple, top of the head — the elbow-on-door posture) does not count.
- **Hand at ear** (built for a frontal camera, where the phone hides behind the hand):
  - a hand box that covers >= 30 % of the ear zone, **or** whose top edge is between the eye
    line and the jaw line with its centre inside the zone's x range (from the front the box
    runs down over palm and wrist, so its centre is often below the jaw line);
  - **or** a pose wrist within 1.3 face widths of the ear landmark (from the front it sits
    ~1 fw below the ear), below the eye line, out at that ear's side (not under the chin),
    elbow raised or out of frame.
  - A hand box centred above the eye line never counts (hand on the head).
- **Driver lock**: the face mesh locks onto the largest face in the driver ROI (during the
  side check) and ignores every other face, e.g. someone behind you. If your face is lost for
  more than 1 s it searches again. The overlay shows `driver locked` / `searching`.

In the debug overlay each ear shows `box± pose± clf <p> hand <s>` (box / pose / classifier
evidence and the hand dwell), and pose wrists are drawn as orange circles.

**Crop classifiers** (colour crops): ear = phone / hand_no_phone / none beside each ear,
mouth = drink / food / none on the lips. When a cup or phone hides the face, both keep
cropping from the last face for 1 s.

> **Ear classifier OFF (2026-10-11).** Its only phone-at-ear data was 3MDAD, whose "front"
> camera is low on the dashboard at 30-45 deg and sees the phone from the side. From a
> mirror-mounted camera the phone hides behind the hand: P(phone) was 0.00 live. Hand-at-ear
> (hands + pose) carries phone calls until frontal phone data (EBDD) exists. In `--guided`,
> `--compare-ear <model dirs>` scores extra ear classifiers side by side once one is on.
>
> **Mouth classifier OFF too (2026-10-11).** On the S01 webcam recording v1 called the cup at
> the lips "food" and v2 (with hand-at-face negatives) called a turned bare face "food"
> (`DATA.md`). Drinking / eating use detector boxes + chewing until frontal data exists. Set
> `mouth_classifier.enabled: true` in the profile to try one (v1:
> `models/mouth_cls_96_v1_ncnn_model`, v2: `models/mouth_cls_96_ncnn_model`).

```bash
python scripts/build_crops.py --3mdad D:/rtdms-data/raw/3mdad/front --every 0.15   # + --ebdd
python scripts/train_crop_classifier.py --kind ear     # -> models/ear_cls_128_ncnn_model
python scripts/train_crop_classifier.py --kind mouth   # -> models/mouth_cls_128_ncnn_model
```

Data and labelling: `DATA.md` (crop classifiers). The training script prints per-class
precision / recall on held-out drivers and writes a contact sheet. `live.py` loads both models
automatically once they exist; key `c` toggles them.

## Guided mode

Prompts, in order: normal (baseline) · phone RIGHT ear · phone LEFT ear · phone held low ·
drinking · eating · talking · **scratching** near the ears (short, a few times) · **hand on
chin** · **elbow on the desk, hand on head**, with short normal gaps. Have a phone, a cup or
bottle and a snack ready. At the end it writes `reports/live_<utc>.md` and `.json`:

| column | meaning |
|---|---|
| hit rate | share of the segment's frames with the expected behaviour active (after smoothing) |
| raw rate | share of frames where the per-frame evidence fired (before smoothing) |
| alerts | behaviour onsets in the segment |
| false alarms | onsets of anything that was not the prompted behaviour |
| time-to-alert | seconds from the prompt to the expected behaviour becoming active |

plus a **setup comparison** for phone at the ear, scored on the same frames for
`hands` / `hands+pose` / `hands+pose+clf`: right- and left-ear hit rate and time-to-alert, and
phone-at-ear false alarms during scratching, hand on chin, elbow-on-head, talking and the
normal gaps.

**Privacy:** by default only the event log (`logs/live_*.jsonl`, behaviour start/end lines) and
the guided summary are written. `--save` additionally writes the raw video and a sidecar to
`data/recordings/` for replay (`eval_events.py ours --src data/recordings`). All gitignored.

## Position the laptop

Laptop at your **front-right**, so your right ear is the near ear (`driver_side: right`):

- Webcam slightly above eye level if you can (books under the laptop), tilted down a little.
- Sit so the webcam is ahead and to your right, ~30–40° off your straight-ahead; your left ear
  is then the "far", partly hidden ear.
- Distance ~60–80 cm; keep both ears, your hands and shoulders in frame (elbows help the pose
  rule but are optional).
- Even, indoor or daylight lighting; avoid a bright window behind you.
- Optionally narrow the ROI: `python scripts/select_roi.py --profile laptop_webcam`.

## Moving to a Pi later

The same profile runs on a Raspberry Pi with a **USB webcam**: capture is plain OpenCV (on
Linux the backend is OpenCV's default, V4L2), detector / pose / classifier are NCNN, face mesh
and hands are MediaPipe (aarch64 wheels). No retraining is needed for the camera change as long
as it is a colour webcam in similar lighting. `--fps-cap` reproduces the Pi's frame rate for
smoothing tests on the laptop. Pi benchmarks and thermal logging are parked.

## What webcam results can and cannot tell us

**Can:** whether rules and smoothing behave sensibly end to end; whether a detector sees a
phone / cup / food in a real hand; how the ear rule, the 3 s dwell, chewing vs talking and the
head-down escalation behave live; comparisons between models, thresholds and ear setups on the
same person and setup.

**Cannot:**

- *General accuracy.* One person, one room, one lighting condition. Treat results as
  "works / doesn't work and why", not as numbers for the report.
- *Night / IR behaviour* (out of scope for the current target).
- *False-alarm rates over hours of real driving.*
