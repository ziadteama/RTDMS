# Phone distraction — evidence

## Settled v1 path

**Ready weights, no local train:** Hugging Face
[`Safe-Drive-TN/State-farm-detection`](https://huggingface.co/Safe-Drive-TN/State-farm-detection)
(YOLOv8n-cls on State Farm c0–c9) → export ONNX → collapse to `{safe, phone, eating}`.

| Artifact | Path |
|---|---|
| Source `.pt` | `models/hf_statefarm/weights/best.pt` |
| Pi runtime ONNX | `models/phone_cls.onnx` (~5.8 MB) |
| Package version | `0.2.0-statefarm-hf` |

AUC: deferred. Local State Farm retrain: optional later, not required for v1.

## Environment

Pi survey baseline: `Subsystems/Raspberry Pi 5 Target.md` (2026-09-20).
No camera / no Hailo at scaffold time.

## G1 — Unit tests

| When | Result |
|---|---|
| 2026-09-20 scaffold | 5 passed (stub) |
| 2026-09-25 wired ONNX | stub + collapse + ONNX smoke — see latest `pytest` |

## G2 — Phone metrics

| When | Source | Notes |
|---|---|---|
| upstream (HF card) | State Farm val | Claims ~99% top-1 — treat as optimistic / possible leakage |
| RTDMS | collapsed phone/eating | **Not yet measured on hold-out**; smoke ONNX runs |

## G3 — Host ONNX smoke (no camera)

| When | Model | n | mean_ms | Notes |
|---|---|---|---:|---|
| 2026-09-25 | `phone_cls.onnx` | 20 | ~11 | `tools/bench_pi.py` on Windows host; includes cold start |
| | | | | **8 passed** pytest (stub + collapse + ONNX) |

## G3b — Pi concurrent bench

| When | Result |
|---|---|
| — | **Open** — run `tools/bench_pi.py` on the Pi with face+physio live |

## Caveats

- State Farm is RGB cabin; IR domain gap remains until custom frames exist.
- Ultralytics-derived weights → AGPL implications for commercial redistribute.
- Standalone latency ≠ concurrent budget.
