# Phone distraction — validation

## Gates

### G1 — Unit / contract (every change)

```bash
cd models/phone && docker compose run --rm verify
# or: pip install -e ".[dev]" && pytest && ruff check src tests
```

### G2 — Phone accuracy (before claiming report objective)

Hold-out **State Farm** (collapsed labels): phone precision/recall such that overall phone
classification meets **≥85%** on the graded phone metric. Eating reported separately.
AUC deferred — not a gate.

### G3 — Pi still-image latency (no camera)

```bash
python tools/bench_pi.py --images path/to/stills --json bench_pi_phone.json
```

Record mean latency, CPU%, RSS with `OPENBLAS_NUM_THREADS=1`. Target: comfortable
headroom at 5 Hz beside face + physiology.

### G4 — Concurrent pipeline (blocked until capture exists)

Face + phone + physiology mock + fusion on Pi; thermal check `vcgencmd get_throttled`.

## Out of scope until camera

Live cabin angles, IR night accuracy, Egyptian custom set fine-tune.
