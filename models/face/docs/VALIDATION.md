# Face subsystem — validation plan

What evidence gates a release of `models/face/`. Numbers that have already been
measured live in `EVIDENCE.md`.

## Gates

### G1 — Deterministic core (required, every change)

```bash
cd models/face
docker compose run --rm verify    # preferred
# or: pip install -e ".[dev]" && pytest && ruff check src tests
```

Covers EAR geometry, hysteresis vs single-threshold chatter, duration-in-ms
(not frames), PERCLOS validity accounting, state-machine short circuits, SNR
quality ratings. **No camera required.**

A change that breaks G1 does not merge.

### G2 — Package install + landmarker load (required before Pi demos)

```bash
pip install -e ".[dev,bench]"
python -c "from mediapipe.tasks.python import vision; assert vision.FaceLandmarker"
test -f models/face_landmarker.task
```

### G3 — Headless replay on a fixed clip (required for results-chapter runs)

```bash
python tests/make_test_video.py
python run.py --video tests/assets/static_test.mp4 --fast --no-display \
              --no-alerts --no-calibrate --log /tmp/face_replay.csv
```

Must complete without exception. CSV is for tooling checks, not accuracy claims
(the clip is a still frame).

### G4 — Throughput benchmark (required once per target machine)

```bash
python bench.py --source image --resolutions --json bench_<host>.json
```

Compare against the laptop baseline in `EVIDENCE.md`. On the Pi 5, also record
`vcgencmd get_throttled` before/after (non-zero throttling invalidates the run).

### G5 — Per-driver calibration quality (required before trusting eye channel)

For each volunteer: run `--calibrate`, record SNR / quality rating
(`good`/`fair`/`poor`). A single accuracy number that ignores this distribution
is not acceptable for the ethics / fairness chapter.

### G6 — Concurrent resource budget (blocked on fusion)

When physiology (and later phone) run on the same Pi, re-measure face FPS,
CPU%, and RSS with the other processes live. Standalone G4 does **not** close
this gate. Tracked as a monorepo-level open question (AI HAT+ necessity).

## Explicitly out of scope for now

- End-to-end "drowsiness accuracy" against induced sleepiness (unethical /
  impractical). Validate components (blink durations vs hand annotation, pose
  vs physical angles, PERCLOS vs scripted closures) instead.
- Phone-usage mAP — belongs to `models/phone/`.
- Cabin alert latency under fusion — belongs to Phase 4.

## Report claims this validation must support

- Vision accuracy ≥ 85% across lighting (component-level evidence + fairness SNR
  distribution, not a single headline %).
- End-to-end system latency < 500 ms (needs G6 + fusion).
- Local / edge only — no cloud paths in this package (already true; keep it).
