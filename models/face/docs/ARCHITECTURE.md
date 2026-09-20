# Face subsystem architecture

## Purpose

Turn cabin-camera frames into quality-gated eye-closure, blink, PERCLOS, gaze,
and head-pose signals for DMS decision fusion. One MediaPipe Face Landmarker
inference per frame; everything after that is arithmetic.

This package does **not** own cabin alerts in the integrated system. It emits a
`StateReport`. Fusion (Phase 4) will combine face + physiology + phone and
drive the buzzer/vibration policy.

## Runtime constraints

- Python ≥ 3.11 (Pi Bookworm 3.11 / Trixie 3.13 both supported).
- Runtime deps: MediaPipe ≥ 1.0 (Tasks API), OpenCV, NumPy.
- No dlib, PyTorch, or TensorFlow.
- Target: Raspberry Pi 5; laptop webcam for development.
- CPU-only path is intentional — Hailo is not required for this landmark model
  (see `docs/EVIDENCE.md` and the vault note on AI HAT+ necessity).

## Data flow

```text
camera / video file
        |
        v
FaceLandmarker (Tasks API) ── one NN inference
        |
        +--> EAR both eyes → median → openness (profile-normalised)
        |         |
        |         +--> blink FSM (hysteresis, duration in ms)
        |         +--> PERCLOS ring buffer (P80)
        |
        +--> iris ratios → gaze deviation
        +--> solvePnP + MP transform matrix → yaw/pitch/roll
                    |
                    v
            eye-channel validity gate (pose limits)
                    |
                    v
            StateMachine → StateReport → (demo Alerter | future DMS fusion)
```

Per-frame work vs 1 Hz decisions are documented in the upstream README
(`docs/UPSTREAM_README.md`). Microsleep escalation bypasses the 1 Hz tick.

## Public contract (fusion-facing)

### `StateReport` (from `dms_face.state`)

| Field | Role |
|---|---|
| `state` | `UNAVAILABLE` / `ALERT` / `DISTRACTED` / `WARNING` / `DROWSY` |
| `reasons` | Human-readable channel explanations |
| `perclos`, `perclos_fast`, `perclos_valid`, `perclos_warming`, `validity` | Slow fatigue channel + quality |
| `closure_ms`, `blink_rate`, `mean_blink_ms` | Fast / medium eye channels |
| `gaze_off_road_s` | Distraction duration |
| `eye_channel_available` | Explicit degrade when eyes cannot be trusted |
| `should_alert` | **Demo only** — ignore in production fusion |

`UNAVAILABLE` / invalid eye channel is the face equivalent of physiology's
null fatigue probability: bad input must not become a confident wrong state.

### `FrameResult` (from `dms_face.pipeline`)

Per-frame telemetry for HUD, CSV logging, and benchmarks. Fusion should prefer
the periodic `StateReport`, not raw landmarks.

## Failure policy

| Condition | Behaviour |
|---|---|
| No face | `UNAVAILABLE`, reason `no face detected` |
| Yaw/pitch beyond EAR limits | Eye channel marked invalid; head-pose distraction continues |
| Validity ratio < 60% | PERCLOS reports unavailable rather than a number |
| Implausible unbroken closure (≥ 30 s) | `UNAVAILABLE` — profile almost certainly wrong |
| Uncalibrated / poor SNR profile | Quality rating `fair`/`poor`; do not paper over with threshold tweaks |
| Sunglasses / occlusion | Degrade to head-pose-only and say so |

## Within-subsystem vs DMS fusion

`StateMachine` fuses the four **face** channels into one report. That is
analogous to physiology turning PPG features into a fatigue probability. It is
**not** the multimodal decision layer. When fusion lands:

1. Face continues to emit `StateReport` (possibly serialised JSON over a socket,
   matching physiology's `OutputSink` pattern).
2. Demo `Alerter` stays behind `--no-alerts` / unused in integrated mode.
3. Cabin alert patterns move to the alert subsystem.

## Divergence from Project 1 report

| Report | This package | Why |
|---|---|---|
| Alert at 2–3 s eye closure | Prolonged threshold 1.5 s | At 100 km/h, 2 s ≈ 55 m blind; literature supports earlier |
| Legacy MediaPipe `mp.solutions` | Tasks API (`mediapipe>=1.0`) | ARM64 packaging removed `solutions` |
| Separate drowsiness vs distraction vision models | One package, two channels | Shared landmarks; phone stays separate |
| AI HAT+ assumed for vision | CPU-only for face landmarks | Model is ~0.07 GOPS; measure before requiring Hailo |

Record further divergences here as they appear.

## Provenance

- Upstream: https://github.com/youssefmedhat4/dms-face
- Imported commit: `65e3afd393545087b310df6a77cd5f3194ee237f` (2026-08-28)
- Monorepo path: `models/face/`
- Primary owner: Youssef Medhat
