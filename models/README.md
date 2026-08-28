# Models

The three detection models described in the Project 1 report (§3.1 System Architecture), plus the
fusion layer that combines them.

| Model | Directory | Detects | Approach | Status |
|---|---|---|---|---|
| Physiology | `physiology/` | Fatigue/stress from HR + PRV | Wrist PPG (MAX30102) → filter → peaks → features → logistic regression | **Implemented** (replay pipeline) |
| Vision — drowsiness | *(pending)* | Eye closure, PERCLOS, blink rate, head pose | MediaPipe Face Mesh → EAR/PERCLOS | Planned |
| Vision — distraction | *(pending)* | Phone usage, gaze deviation | YOLOv5 object detection + gaze/head-pose | Planned |

Decision fusion consumes all three and owns the alert decision. No individual model emits an alert
on its own — see the physiology subsystem's architecture doc for why that boundary matters.

## Naming note

`physiology/models/` (nested) holds **trained model artifacts** (JSON), not subsystems. The outer
`models/` directory here holds the subsystems. The nesting is inherited from the upstream project
layout and its Dockerfile; renaming it would be churn for cosmetics.

## Adding a new model

Follow the shape `physiology/` already establishes:

```
models/<name>/
├─ pyproject.toml       pinned runtime + dev/train extras
├─ Dockerfile           multi-stage: base → development → runtime
├─ compose.yaml         `verify` (test+lint+typecheck) and a run/simulate service
├─ configs/             tunable defaults, not hardcoded constants
├─ docs/
│  ├─ ARCHITECTURE.md   contracts, data flow, failure policy
│  └─ VALIDATION.md     what evidence gates a release
├─ src/<package>/
├─ tests/
└─ tools/               training, benchmarking, dataset validation scripts
```

Key conventions worth carrying over, because they are what make the physiology subsystem
Pi-deployable:

- **Runtime deps stay minimal.** Training-only dependencies (scikit-learn) must not enter the
  runtime path. Export trained models as plain JSON/ONNX artifacts — never unpickle at runtime.
- **Quality gating is not optional.** A model must be able to say "I don't know" (null output) when
  its input is bad, rather than emitting a confident wrong number.
- **Fusion owns thresholds and alerts.** Models emit continuous scores and quality state.
- **Docker is the canonical environment**, so verification does not depend on the workstation's
  Python version.
- **Resource budgets are explicit** and validated on the actual Pi with the other models running
  concurrently — a standalone benchmark proves nothing about contention.
