---
title: "Models Index"
tags:
  - subsystem
  - moc
  - implementation
---

# Models Index

↑ [[Home]]

The detection models from [[3.1 System Architecture]], plus the fusion and alert layers that
consume them. Code lives in `models/`; see `models/README.md` for on-disk conventions and
**ownership rules for parallel work**.

## Status

| Model | Note | Code | Detects | Status |
|---|---|---|---|---|
| Physiology | [[Physiology Subsystem]] | `models/physiology/` | Fatigue/stress from HR + PRV | **Replay pipeline implemented** |
| Face (drowsiness + gaze) | [[Face Subsystem]] | `models/face/` | Eye closure, PERCLOS, blink, gaze, head pose | **Core + demo runner** |
| Vision — phone | *(pending)* | `models/phone/` *(not yet)* | Phone usage | Planned |
| Decision fusion | *(pending)* | *(pending)* | Combines models → risk level | Planned (Phase 4) |
| Alert subsystem | *(pending)* | *(pending)* | Buzzer + vibration patterns | Planned (Phase 4) |
| Wearable firmware | *(pending)* | *(pending)* | ESP32-C3 + MAX30102, BLE only | Planned (Phase 1) |

> [!note] Report listed two vision models
> Project 1 split "drowsiness" and "distraction". In code, **face landmarks are one inference**,
> so EAR/PERCLOS/gaze/head-pose share `models/face/`. Phone detection stays a separate package so
> YOLO/Hailo work does not conflict with MediaPipe work. Recorded as a divergence in
> `models/face/docs/ARCHITECTURE.md`.

## Parallel-work ownership

| Zone | Owner | Path | Branch |
|---|---|---|---|
| Face | Youssef | `models/face/` | `face/<topic>` |
| Physiology | Ziad | `models/physiology/` | `physio/<topic>` |
| Phone | TBD | `models/phone/` | `phone/<topic>` |
| Shared status docs | Tiny PRs only | root README, `models/README.md`, this note, `CLAUDE.md` | `docs/<topic>` |

**Binding rule for every agent:** `.cursor/rules/git-branching.mdc` — trunk-based, one zone per
branch/PR, no model commits on `main`. Narrative: `models/README.md` → Ownership.

## Architectural principles

These emerged from the physiology subsystem and must hold across all models — they are what
make the system Pi-deployable and scientifically defensible rather than a demo.

> [!important] 1. Models report, fusion decides
> No model emits a **production** alert. Each emits a continuous score plus a quality/confidence
> state. Fusion owns thresholds and alert policy. (Face `run.py` may buzz for local demos;
> `StateReport.should_alert` is not the cabin API.)

> [!important] 2. Every model must be able to say "I don't know"
> Quality gating is not optional. Bad input → null / `UNAVAILABLE` output, not a confident guess.
> A sunglasses occlusion or a motion artifact must degrade the output explicitly, because
> [[4.4 Feasibility and Risk Analysis]] rates missed detection and false alarms as the top risks.

> [!important] 3. Quality gates outputs; it is never a model feature
> Otherwise a model learns to mistake artifacts for the thing it is detecting. Ablation must
> confirm this per model.

> [!important] 4. Training deps never enter the runtime path
> Export to plain JSON/ONNX/task artifacts; never unpickle at runtime. Keeps the Pi image small and
> the runtime auditable.

> [!important] 5. Resource budgets are validated concurrently
> All models share one Pi 5. A standalone benchmark proves nothing about contention — the gate is
> measured with the other models running, including a thermal soak.

## Shared constraints

From [[3.2 Technical Description]]:

- End-to-end latency **< 500 ms**; Pi↔wearable trigger **< 100 ms**
- Vision accuracy **≥ 85%** across lighting conditions
- Operating range **−10 °C to 50 °C**
- **Local processing only** — no cloud, no persistent biometric storage ([[4.3 Ethics]])

## Integration order

Per [[5.2 Phase Two Plan]] and the staged mitigation plan in [[4.4 Feasibility and Risk Analysis]]:
validate each module standalone → define thresholds → integrate one condition + one output →
add the rest → full-scenario testing. Do not build the whole system at once.
