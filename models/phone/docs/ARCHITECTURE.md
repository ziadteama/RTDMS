# Phone distraction architecture

## Purpose

Emit quality-gated **phone** and **eating** distraction scores for DMS fusion from cabin
frames. One YOLOv8n-cls (ONNX on Pi) covering both behaviours. Does **not** own cabin alerts.

## Pi constraints (binding)

- Infer at **5 Hz** default (alert-within-1s requirement; save CPU for face + physiology).
- Input **224 px**; ONNX Runtime with `intra_op_num_threads=1`.
- No Ultralytics/PyTorch on the Pi runtime path.
- Concurrent budget must be measured with face + physiology live — see
  `.cursor/rules/pi-performance-pipeline.mdc`.

## Data flow

```text
frame (from shared capture, decimated)
        |
        v
ONNX YOLOv8n-cls (State Farm c0..c9)
        |
        v
softmax collapse → {safe, phone, eating}
        |
        v
quality gate → PhoneOutput JSON → /run/dms-phone.sock → dms-fusion
```

**v1 weights:** open Hugging Face `Safe-Drive-TN/State-farm-detection` exported to
`models/phone_cls.onnx`. Stub detector only if that file is missing.

## Class map (v1) — State Farm primary; AUC deferred

Primary open dataset: **State Farm Distracted Driver** (Kaggle). Same 10-class
taxonomy as AUC; no signed license gate.

| State Farm / AUC-style labels | Our class |
|---|---|
| c0 normal / safe driving | `safe` |
| c1–c4 texting / talking phone (L/R) | `phone` |
| c6 drinking (+ eating if present) | `eating` |
| c5 radio, c7 reach behind, c8 makeup, c9 passenger | `safe` for v1 (revisit later) |

**AUC** (named in Project 1 §3.3) is **deferred** — not required; no supervisor
insistence. If obtained later, use the same collapse map.

Graded report metric remains **phone** accuracy ≥85–90%.

## Fusion contract (`PhoneOutput.to_dict`)

| Field | Meaning |
|---|---|
| `phone_score` / `eating_score` | Probabilities; **null** when quality BAD |
| `top_class` | `safe` \| `phone` \| `eating` \| null |
| `sustained_*_ms` | Time above threshold |
| `quality.state` | `good` / `degraded` / `bad` |

Fusion policy (not this package): sustained phone → continuous buzzer (report Table 3-2);
eating → milder pattern; face `DISTRACTED` may corroborate phone-in-lap.

## Failure policy

| Condition | Behaviour |
|---|---|
| Missing model file | Stub or BAD + `NO_MODEL` |
| Empty frame | BAD + null scores |
| Low confidence | DEGRADED; scores still emitted |
| Inference exception | BAD + null scores |

## Divergence from report

Report named YOLOv5 object detection + AUC. v1 uses **ready YOLOv8n-cls ONNX** (Safe-Drive-TN /
State Farm) with class collapse. No local train required for the first runnable path. AUC deferred.
OD/Hailo HEF remains a later upgrade.
