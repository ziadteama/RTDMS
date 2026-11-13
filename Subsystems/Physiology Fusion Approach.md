---
title: "Physiology × Fusion Approach (Garmin confirm path)"
tags:
  - subsystem
  - physiology
  - fusion
  - garmin
  - plan
aliases:
  - Physio fusion approach
  - Garmin fatigue approach
status: agreed-approach
code_path: models/physiology
---

# Physiology × Fusion Approach (Garmin confirm path)

↑ [[Home]] | [[Physiology Subsystem]] | [[Models Index]] | code: `models/physiology/` · fusion stub: `fusion/`

How physiology should serve RTDMS **decision fusion**, given the live sensor is the **Garmin FR265
RR stream** (not MAX30102-first for this path). Agreed 2026-11-13.

> [!important] Role in the product
> Physiology is a **confirming / escalating** channel for behavioural risk — especially face
> drowsiness — not a standalone “driver is drowsy” alarm. That matches [[3.1 System Architecture]]
> Table 3-2 (max alert = combined behavioural **and** physiological risk) and the fusion stub
> (`fusion/`: `physio confirms` → `MAX` only when face/phone already elevated).

## What fusion consumes

| Field | Rule |
|---|---|
| `fatigue_probability` | Continuous `[0,1]` **or** `null` |
| Quality / HRV state | `BAD` / gaps / warmup → probability stays **`null`** (never invent a score) |
| Alert thresholds | **Owned by fusion**, not by the physiology model |

Models **report**. Fusion **decides**. Demo buzzers inside model `run.py` files are not the
production path ([[Models Index#Architectural principles]]).

Current stub behaviour (thresholds still calibration stubs):

```text
face drowsy  → REPEATED
phone sustained → CONTINUOUS
fatigue ≥ 0.7 + (REPEATED|CONTINUOUS) → MAX   ("physio confirms")
fatigue ≥ 0.7 alone → SHORT_BEEP only         (weak nudge, not the product pitch)
```

## Why we do not need a watch sample to design training

The Connect IQ app and Pi receiver already fix the contract
(`models/physiology/docs/packet_format.md`):

- Watch writes BLE packets with **RR intervals in ms** (+ optional HR).
- Pi runs `RrHrv` → `FeatureSnapshot.model_features()` → optional logistic JSON →
  gated `fatigue_probability`.

Schema and feature columns are known from that app. A live session is for **validation and
calibration**, not for inventing the training plan.

## Training strategy (fusion-aligned)

### Tier 0 — Bring-up prior (done / in flight on `physio/*`)

- Public **WESAD** Base vs TSST labels → Empatica IBI (or BVP) → same `RrHrv` features →
  `fatigue_wesad_v1.json`.
- Purpose: wire `--model`, LOSO plumbing, evidence docs.
- **Not** the graded “drowsiness detector” claim. Lab stress ≠ cabin drowsiness; E4 IBI ≠ Garmin
  optical RR. Treat metrics as experimental ([[Physiology Subsystem#Open risks]]).

### Tier 1 — What the project should optimize for (next)

1. Run face + Garmin together on the Pi (shared capture / concurrent budget rules still apply —
   [[Pi Setup Plan]], [[Raspberry Pi 5 Target]]).
2. **Log** RrHrv feature windows (or raw RR) with coarse labels aligned to face state:
   - `normal` / `drowsy` (and optionally distracted) from face reports or manual tags.
3. Retrain the **same** small logistic on those windows (still JSON artifact, sklearn train-only).
4. Retune fusion’s ~0.7 confirm gate on joint replays — prefer **high precision on confirm** over
   high physio-only recall.

That dataset matches both the **real sensor** and the **real fusion job** (confirm drowsy).

### Tier 2 — Optional later

- Chest-strap / ECG agreement for RR quality (domain check).
- Official WESAD synchronized `.pkl` labels if we need a cleaner public baseline than quest+E4.
- Do **not** merge physio into a joint neural net with face/phone to “save processes” — keep
  separate sockets into fusion ([[Pi performance pipeline]] / project rules).

## Validation checklist (watch connected)

Use a live FR265 session to prove the **pipeline**, then to gather Tier 1 labels:

- [ ] Packets decode; `seq` gaps handled; no fabricated RR on loss
- [ ] `RrHrv` reaches `VALID` / `DEGRADED` in quiet sitting; goes null/BAD under motion as designed
- [ ] With `--model`, `fatigue_probability` is set only when state allows
- [ ] Fusion probe: face drowsy + high fatigue → `MAX` / `physio confirms`
- [ ] Concurrent with face (and distraction/phone as available): RSS/CPU still inside budgets

## Explicit non-goals

| Non-goal | Why |
|---|---|
| Beat WESAD stress AUROC as the release gate | Wrong label for cabin drowsiness / fusion confirm |
| Physio-only continuous buzzer as primary UX | Report + stub escalate *combined* risk |
| Waiting on MAX30102 before any fatigue score | Garmin RR path is the live wearable we have |
| Training stacks on the Pi | Export JSON/ONNX-style artifact offline; Pi loads weights only |

## Pointers into the code vault

| Topic | Where |
|---|---|
| Subsystem narrative | [[Physiology Subsystem]] |
| Packet + clocks | `models/physiology/docs/packet_format.md` |
| WESAD → Garmin features | `models/physiology/docs/WESAD.md` |
| Evidence / LOSO numbers | `models/physiology/docs/EVIDENCE.md` |
| Fusion stub | `fusion/README.md`, `fusion/src/dms_fusion/__init__.py` |

## Status snapshot

| Piece | State |
|---|---|
| Fusion role (confirm) | **Agreed** — document of record |
| Garmin RR → features → sink | **Implemented** |
| WESAD bring-up artifact | Experimental prior (see physio branch / EVIDENCE) |
| Face-aligned Garmin labeled retrain | **Next** |
| Fusion threshold calibration on Pi | **Next** after labeled logs |
