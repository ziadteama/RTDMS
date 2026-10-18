# Distraction module architecture

## Purpose

Detect, from the centre-mirror fisheye IR camera, five driver behaviours: phone at the right
ear, phone at the left ear, phone held low / texting, drinking, eating. Normal driving reports
nothing. Runs on the Raspberry Pi 5 CPU; an AI HAT+ may take the detector later.

This package **reports** per-behaviour states with a *recommended* level (`warning` / `alert`).
In the integrated RTDMS, fusion owns the cabin buzzer (repo invariant) and may use, downgrade or
combine these levels. See "Divergences" below.

## Data flow

```text
camera 1296x972 (OV5647 full-FOV 2x2 binned; 1920x1080 would be a centre crop)
   |  picamera2 YUV420 -> Y plane = grayscale for free; PC: BGR -> gray
   v
DriverROI.apply            fisheye -> virtual pinhole aimed at the driver ROI (precomputed
   |                       CV_16SC2 maps, one cv2.remap), or a plain crop when rectify is off
   |                       + optional passenger mask polygons
   v  gray -> 3 channels (only now, on the small view)
   +--> Detector (every Nth frame)   YOLO26n, letterbox 416, NCNN on the Pi
   |        classes: phone / drink / food / hand (COCO baseline maps 12 COCO classes)
   +--> FaceMesh (every frame)       FaceCropper -> MediaPipe Face Landmarker (or models/face's
   |        landmarker) on a 256 px face crop -> landmarks back in view pixels
   |        -> FaceAnalyzer: pitch/yaw, gaze-down, jawOpen, lip ratio
   +--> MediaPipeHands (every Nth frame, baseline only; COCO has no hand)
   v
RuleEngine.evaluate        geometry in face-size units + per-drive baseline + chewing analyser
   |                       -> Evidence per behaviour: True / False / None (cannot judge)
   v
BehaviourSmoother x5       sliding window (1.75 s) + hysteresis (on 70 %, off 30 %)
   v
levels -> FrameResult      per-frame dict  -> EventLog (JSONL start/level/end) -> viz overlay
```

All rule geometry happens in the **rectified driver view**. Its intrinsics are known exactly
(the virtual camera `P`), so solvePnP head pose is metric there; without calibration the usual
focal ≈ width guess is used and only baseline-relative pitch is meaningful.

### Why a face crop

At a mirror mount the driver's face is ~100 px wide in the driver view. MediaPipe's face
detector runs at 128x128, so on the whole view a 66 px face is already missed (measured: 0/90
frames) while the face crop still tracks a 42 px face (88/90). See EVIDENCE.md. The cropper
searches overlapping tiles (one per frame) until a face is found, then follows it with a
square crop of 2.2x the face size that moves only with hysteresis, so MediaPipe's
detect-then-track sees a steady image.

## Coordinate conventions

- Landmark 234 is always the **driver's right** face side, 454 the **driver's left**. With the
  driver facing the camera, 234 appears on image-left. Never mirror the input.
- `driver_side: right` (left-hand drive) puts the camera to the driver's right: the right ear is
  the near, fully visible one; the left ear is the far one, partly hidden behind the head.
  `driver_side: left` swaps them. The far ear zone reaches `inward` fw behind the ear landmark
  and accepts a hand alone as evidence (phone hidden), at `hand_only_confidence`.
- Distances are in `fw` = max(|234-454|, |10-152| / 1.1): face width, kept stable under yaw.
- Pitch: positive = head down. Yaw: positive = face toward image-right. Both relative to the
  per-drive baseline (median of the first 10 s with a face), because the camera is off-axis.

## Rules (thresholds: configs/rules.yaml)

| Behaviour | Frame evidence |
|---|---|
| phone at near ear | phone box overlaps (∩ / min area ≥ 0.25) the near-ear zone |
| phone at far ear | same with the far-ear zone (reaches `inward` behind the head) |
| hand at either ear | hand box (MediaPipe or detector) covering >= 30 % of the ear zone, or with its top edge between eye and jaw line and its centre in the zone's x range (frontal camera: the box runs down over palm and wrist); or a pose wrist within 1.3 fw of the ear landmark, out at that ear's side, not above the eye line, elbow raised or unseen; a box centred above the eye line never counts; held >= 3 s (gap-tolerant) -> WARNING; a phone box in the zone or ear-crop classifier P(phone) >= 0.6 during the episode -> ALERT. Ear zones span eye line .. jaw line |
| phone in hand | phone not at an ear, centre below chin − 0.1 fw, within 0.3 fw of a hand box (skipped when hands are off), outside holder zones. Level escalates to `alert` after head pitch ≥ 15° or gaze-down above baseline for ≥ 2 s |
| drinking | drink box overlaps the mouth region (lips 13/14, corners 61/291; 0.40 x 0.35 fw half-sizes); pitch-up ≥ 8° multiplies confidence by 1.25 |
| eating | food box within 0.8 fw of the mouth in the last 5 s **and** chewing: over a 3 s window the detrended jaw signal has enough amplitude, ≥ 45 % of its 0.3–7 Hz power in 0.8–2.5 Hz with the peak there, and lips closed (gap/width < 0.10) in ≥ 60 % of frames. Talking (jaw ~4–5 Hz, lips apart) and singing (mouth held open) fail the last two tests |

Jaw signal: blendshape `jawOpen` with the MediaPipe backend; with the dms_face LiteRT backend
(no blendshapes) it falls back to chin–nose distance in fw, with its own amplitude threshold.
Gaze-down: blendshapes `eyeLookDown − eyeLookUp`, or iris drop below the eye-corner line.

## Per-frame contract (`FrameResult.to_dict()`)

```json
{"t": 12.4, "level": "warning",
 "behaviours": {"phone_in_hand": {"active": true, "level": "warning", "confidence": 0.71,
                "ratio": 0.83, "raw": true, "holding": false, "why": "phone below face, ..."},
                "...": "..."},
 "face": {"pitch": 3.1, "yaw": -4.0, "gaze_down": 0.05, "gaze_source": "blendshape",
          "jaw": 0.12, "jaw_source": "blendshape", "lip_ratio": 0.04} | null,
 "head_down": false, "head_down_s": 0.0,
 "chewing": {"chewing": false, "hz": 0.6, "band": 0.2, "amp": 0.01, "lips_closed": 0.9},
 "detections": [{"cls": "phone", "conf": 0.66, "box": [x1, y1, x2, y2], "src": "detector"}],
 "baseline": {"ready": true, "progress": 1.0, "pitch": 2.0, "yaw": -3.1, "gaze": 0.02},
 "timings_ms": {"rectify": 1.5, "detect": 30.4, "facemesh": 8.6, "hands": 5.8, "rules": 0.3}}
```

Event log (`logs/drive_<utc>.jsonl`): `session_start`, then `start` / `level` / `end` per
behaviour (`end` carries `duration_s` and `peak_level`), `session_end`. `--per-frame-log` adds
one `frame` record per frame for event-level evaluation. No images, no landmarks.

## Failure policy

| Condition | Behaviour |
|---|---|
| No face / face occluded | for up to `face_geometry_hold_s` (5 s) the last face's zones are reused, so detector evidence (phone at an ear, cup at the mouth) still counts; face-only signals (chewing, head pose, phone below the chin) pause. Beyond that every behaviour's evidence is `None`: states **hold**, then clear after `face_lost_hold_s` |
| Baseline not ready (first ~10 s) | head-down escalation and the pitch-up drinking bonus are off; `baseline.ready=false` in the output |
| No hand source (`hands.source: off`) | phone-in-hand no longer requires a hand; far-ear hand-only evidence is impossible |
| Missing calibration file with `rectify.enabled` | refuses to start (say `--no-rectify` explicitly) |
| ROI reaches > 85° off-axis | refuses: a pinhole view cannot hold it |
| Unknown config key | refuses to start (typos never silently fall back to defaults) |

## Divergences

| Source | This package | Why |
|---|---|---|
| Repo invariant "models report; fusion decides" | Module emits `warning`/`alert` levels per the task spec | Levels are recommendations in the output; fusion remains the owner of the buzzer. Revisit when fusion consumes this module |
| `models/phone` (State Farm YOLOv8n-cls) | Separate package, object detector + rules | State Farm is a passenger-side view; this camera is at the mirror. Whole-image classifiers do not transfer across mounts |
| Earlier `dms_distract` draft (Hailo, YOLOv8n, stationarity instead of hands) | YOLO26n on CPU/NCNN, MediaPipe hands for the baseline, explicit left/right ear rules | Task spec; Hailo stays a later option |
| Spec: "face mesh on the face crop" | Implemented as a tracked, hysteresis-moved crop with tiled search | Measured necessity for small faces (EVIDENCE.md) |
| Spec: jawOpen blendshape | Used when available; geometric fallback for the LiteRT backend | models/face's Pi backend has no blendshapes |
| YOLO26 end-to-end (NMS-free) head | Ultralytics 8.4.175 NCNN/ONNX export kept the raw one-to-many head (84 x 3549); decoded with NMS here | Decoder accepts both heads |
| Spec: face lost → hold | Hold, but clear after 5 s | An alert must not stick on a driver who left the view |
