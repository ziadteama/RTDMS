# Pi live drinking + phone (23 Nov 2026)

Checkpoint tag: **`papa-johns`** (`demo/held-drinking`). Session notes for the live IR
demo debug after [[../Subsystems/Handoff 2026-11-23 Demo]] (on `main`).

## Goal

On the centre-mirror NoIR camera: **sip → drinking**, **phone at ear → call**, without
retraining, without bringing back the daylight COCO detector, and without wrecking FPS.

## What was wrong (measured)

### Drinking used the wrong signal

The demo dashboard averaged the action classifier’s `p_drinking` (loose upper-body crop). A
phone or hand at the cheek scored 66–89% “drinking” until the top label flipped to call.
Fusion ignored drinking; the light still looked broken.

The mouth path already existed (`scripts/held_live.py`, `stream.py --held`) but the Pi camera
flags were `--hybrid --no-detect` only — **`--held` was off**.

### Cup threshold ignored the product file

`held_live.py` hardcoded `P_OBJECT = 0.95` (SynDD food3 sweep). Product IR params in
`models/held_v1/held_params.json` are **`p: 0.5`**. Live sips sat at object **0.75–0.94** with
the box drawn and still showed “not drinking.”

### Daylight COCO killed FPS

With the hand near the mouth, `held` stage was **~120 ms** and stream FPS fell to **~12**.
The optional COCO drink/food detector (colour daylight weights) was the heavy piece. Dropping
it brought idle/near FPS back to **~23–30**.

### Crop missed the bottle

`object` is only `P(cup)+P(food)` inside a **128 px** square from mouth↔wrist geometry — not
“bottle anywhere in the frame.” The old midpoint / 2× face-height box often covered **face +
hand** while the bottle body hung outside → scores collapsed to **0.01–0.06** with a visible
bottle. Fixed with a **hand-weighted, taller, slightly lower** `grip_crop`.

### Eating sticky label

One frame with `food > cup` set `kind=eating` and it stuck for the episode. IR product path
now reports **drinking only**.

### Phone call: ear saw the phone, latch did not

Call alert required top class **`call` ≥ 70% of the last 2 s** *and* mean ear > 0.5. During
real calls the action often topped as **`drinking`**, so:

- ear showed **100%** (after we also scored ear on drinking / hand_on_face),
- drinking stayed **off** (ear veto into `held`),
- dashboard still said **PHONE: none** because the 70% top-class=call window never filled.

Yellow dots are **pose wrists** (COCO 9/10), not fingertips; they can look misplaced on IR
side views. The drinking box uses an extrapolated grip point, not those dots alone.

## Fixes applied (this branch)

| Change | Where |
|---|---|
| Enable `--held` on Pi camera args | `pi/src/rtdms_pi/sources.py`, `models/distraction/pi/start_stream.sh` |
| Dashboard prefers `held` over `p_drinking` average | `demo/dashboard/server.py` |
| Cup threshold from `held_params.json` `p` | `scripts/held_live.py` |
| Drop COCO; slower pose (~6.7 Hz); 1 pose thread | `scripts/held_live.py` |
| `grip_crop` (hand-weighted bottle box); drinking-only kind | `scripts/held_live.py` |
| Ear scored on call / drinking / hand_on_face | `scripts/hybrid.py` |
| Held phone veto: latched call/texting **or** ear > 0.5 | `scripts/stream.py` |
| Call alert path A: ear > PHONE_P on ≥ 70% of 2 s window | `scripts/hybrid_alerts.py` |
| Deploy ships `held_live` + `held_v1` | `pi/deploy/deploy.sh` |

## How to verify on the Pi

1. Sip with bottle at lips → **DRINKING**, box covers bottle, object stays high, FPS ~20+.
2. Phone at ear → **PHONE CALL** within ~2 s, **not drinking** (even if action says drinking).
3. Bare hand on cheek → neither drinking nor call.

Record with `demo/tools/session_log.py`; analyse with `demo/tools/analyse.py` or the scratch
scripts under `_scratch/` (local only, not committed).

## Not done / follow-ups

- Concurrent Pi budget with physio + fusion still open.
- Fusion still does not alert on drinking (D28); dashboard is detection display.
- Optional later: fingertips / MediaPipe Hands — rejected for head-pressed hands + cost; ear
  veto is the cheap phone fix.
- `papa-johns` marks drinking working; call ear-majority landed after that tag — retag or add a
  second checkpoint when committing.
