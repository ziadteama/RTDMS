# DMS fusion stub

Consumes model OutputSink JSON and maps risk → alert pattern. **Owns** cabin alert
decisions. Models only report scores + quality.

Pi-first: keep this process tiny; no ML here.

## v0 behaviour

- Reads the latest in-memory / file replay dicts from physiology, face, and phone.
- Escalates: phone sustained → continuous; face drowsy → repeated; physio fatigue confirms drowsy.
- GPIO optional later.

```bash
cd fusion
pip install -e ".[dev]"
pytest
python -c "from dms_fusion import stub_demo; stub_demo()"
```

## Concurrent no-hardware simulation

Assesses CPU/RSS/latency with face + phone + physiology + fusion together (still image,
synthetic PPG, ONNX phone — no camera/ESP):

```bash
py -3.12 fusion/tools/sim_concurrent_pipeline.py --seconds 30 --json fusion/bench_sim.json
```

Write-up: [`docs/PIPELINE_SIM_ASSESSMENT.md`](docs/PIPELINE_SIM_ASSESSMENT.md).
