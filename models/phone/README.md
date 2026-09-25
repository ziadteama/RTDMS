# Phone / eating distraction (dms-phone)

Multi-class cabin distraction scores for DMS fusion: **safe / phone / eating**.
Pi-first: ONNX at ~5 Hz from open State Farm YOLOv8n-cls weights (Safe-Drive-TN), with
c0–c9 collapsed to three classes. Models report; fusion decides alerts.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Branch zone: `phone/<topic>`.

## Quickstart

```bash
cd models/phone
pip install -e ".[dev,runtime]"
pytest
docker compose run --rm verify
```

Smoke (no camera):

```bash
python tools/bench_pi.py --n 30 --json bench_host.json
```

Optional local fine-tune later (not required for v1):

```bash
pip install -e ".[train]"
python tools/prepare_statefarm.py --raw data/raw_statefarm --out data/collapsed
python tools/train_cls.py --data data/collapsed
python tools/export_onnx.py --weights models/runs/.../best.pt
```

## Pi rules

Always apply `.cursor/rules/pi-performance-pipeline.mdc`: concurrent budget, shared capture,
ONNX on device, no PyTorch runtime on the Pi.
