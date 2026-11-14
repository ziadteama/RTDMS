# Held object near the face

Updated2026-11-14. Current work: overnight/held-object. Nano128 is product; s is control. No production phone/pipeline edits.

## Phase A completed

The first Nov8 attempt was sandbox-blocked. Full-access audit, geometry, crop construction and training later ran; that initial blocker is historical, not current status. Original datasets/shipped weights were not modified.

Release wrist confidence>=.3; mouth=(mesh13+14)/2; face height=norm(mesh10-mesh152). Cached NCNN/PyTorch wrist agreement mean.1036 face heights,91.7% within.25. Original wrist gate misses low-held bottles; DAD drink34/664 passed h0/K1. Mouth fallback mesh?held<=1s?pose raises that to260/664. D26 full geometry/caches and larger contact sheets are under _held_data/geometry_v2 and _held_data/sheets.

Loose crop gate h=.35,K=1.25; hand=wrist+.35*(wrist-elbow), usable elbow>=.3 else wrist. Crop midpoint mouth/hand; square side=max(2 face heights,1.3 mouth-hand distance), replicate padding,128px gray, per-crop1?99% stretch (span<8 unchanged). Tight flag uses h0 distance<=1 inside the saved loose corpus. Min.3s between crops per clip.

Retained22612 of39465 eligible crops; tight12399; food1161. Only TRAIN and SynDD-val crops; no test training crops. Crops outside loose gate are not silently added. No automatic label corrections.

| Class | Dataset | Split | Loose retained | Tight |
|---|---|---|---|---|
| cup_bottle | 3mdad | train | 3658 | 1960 |
| cup_bottle | syndd | train | 745 | 499 |
| cup_bottle | syndd | val | 211 | 132 |
| empty_hand | 3mdad | train | 9716 | 4725 |
| empty_hand | ebdd | train | 374 | 210 |
| empty_hand | syndd | train | 5325 | 3471 |
| empty_hand | syndd | val | 1422 | 805 |
| food | ebdd | train | 251 | 74 |
| food | syndd | train | 719 | 428 |
| food | syndd | val | 191 | 95 |

Sheet review by orchestrator: cup tight~46/48 show cup/bottle; empty_hand hard negatives appropriate. Food only~7/48 visibly food, dominated by SynDD40908. ALL original food is excluded from binary training, including CLIP-empty predictions. Food hidden by the hand is a weak-label caveat, not negative ground truth.

## Phase B and versioned v2

Original tight/loose/driver60 fits and v2 nano/control are preserved under _held_data/phaseB and held_object_v2. Versioned manifest SHA25693f349326c7835c2fdab2dde30ce80feb1ed61e1c8d89dee52e84d5e4c816565. Original1161 food crops: provisional CLIP k6 groups264 food-visible,81 empty,816 uncertain; cluster sheets still need visual inspection. Five driver-disjoint OOF diagnostic fits flag suspects; none relabelled. Human food-label results are not consumed tonight.

INT8 remains BLOCKED: ncnn2table WinError4551. No executable/policy change attempted. FP32 NCNN works. Pi unreachable previously; no Pi/SSH contact overnight. Pi wrist/IR classification/concurrent latency remain open, PC?2.1 latency is estimate only.

## Timing correction and overnight baseline

Old0.3s rule could not cover3fps. D34 cadence correction uses effective window max(window,2.5 median interval); coverage>=2 eligible samples or80% span; sip>=2 consecutive confirmed samples spanning max(dt,.5-.5dt).25 tests pass3/10/20fps. Compare ea3d6ad/c77e01c on nano SynDD-val: tied11/15,0 ALL-negative FA/h; keep c77e01c as one runtime path.

All current FA/h = false drinking onsets / ALL non-drinking hours. [results.md](results.md) has separate validation/test tables and detector/control rows. Historical normal-only rates remain archived and explicitly labelled, not silently compared. Product nano test (report only): SynDD11/18,4.6317 FA/h;3MDAD29/30,11.6931 FA/h; DAD2/2,0 FA/h. Do not pick a change using DAD2clips.

Frozen MDAD-val drivers10,11,15,19,50 (seed28), removed from all subsequent nano/control training. Existing models are contaminated on that new holdout; clean retrain in progress:18076 train crops,3375 crop-val. Event validation uses all15 mapped actions per heldout driver. Choice uses validation only; test scored after keep. [OVERNIGHT_PLAN.md](OVERNIGHT_PLAN.md), [overnight_log.md](overnight_log.md), and [morning_report.md](morning_report.md) track the run.

Source data, phone/ear/lap/action weights, runtime scripts and Pi start config remain unchanged. No data deleted or pushed.

## Overnight result (2026-11-14, 04:00–10:00) — current state

Model version: **overnight iteration 6 nano** (`_held_data/overnight/distill_rw/weights/best.pt`,
FP32 NCNN `best_ncnn_model`): clean-trained without the 5 frozen 3MDAD-val drivers, distilled
from the s control with dataset x class sampling. Dataset version: held_object_v2 (manifest
sha256 `93f34932…`). Rule c77e01c, p=0.9, x=5, window=0.5, gate h=0.35/K=1.25, **phone
call/texting veto at fusion** (`pi_held/held_params.json`). Pi runtime: `src/held_runtime.py`
(0 mismatches vs the evaluated geometry on 1,072 cached frames; smoke-tested on a real frame).

| | SynDD | 3MDAD | DAD (2 drinks) |
|---|---|---|---|
| Validation | 11/15, 0 FA/h | 9/10, 0 FA/h | — |
| Test (report only) | 12/18, 0 FA/h (16/18 with untrimmed windows) | 29/30, 2.42 FA/h | 0/2, 0 FA/h |
| Old box detector, test | 15/18, 0 FA/h | 22/30, 5.24 FA/h | 2/2, 8.67 FA/h |

Target (≥ 85 % recall, ≤ 5 FA/h everywhere) not reached: SynDD recall is the gap. Kept: phone
veto (it2), distillation (it4), dataset x class sampling in distillation (it6). Reverted: yawn veto
(it3), plain dataset sampling (it5), stronger augmentation (it7), cup class weight (it8).
Skipped: phone/cigarette hard negatives. Eating still unsupported (experimental rule SynDD-test
0/19); 1,161 crops queued in `label_food_v2.html`.

**Pi wrist check: NOT DONE** — Pi unreachable, no contact allowed overnight. Run
`pi_held/run_pi_eval.sh` (writes `wrist_check.jpg`) once the Pi is up; record the result here.
Details: [morning_report.md](morning_report.md), [results.md](results.md),
[overnight_log.md](overnight_log.md).

## IR run (2026-11-14 evening → 11-15) — current state, supersedes the overnight section

**Product drinking model:** IR-4 nano (`_held_data/ir/camsim_light/weights/best.pt` /
`best.onnx`).
- Recipe: clean nano + distillation from s, dataset × class sampling, 1,500 phone hard negatives,
  light camera simulation.
- Rule p=0.5, x=10, window=0.3, gate h=0.35 / K=1.25, phone veto.

**Eating:** GRU head on IR-3 backbone features (`eat_backbone_ir3.onnx` + `eat_head.onnx`),
gated on ≥ 2 hand-at-mouth samples, phone veto, no eating during drinking.

**Dataset version:** IR split `ir_split.json` (SynDD + DAD front IR), untrimmed windows.

| IR | Drinking | Eating |
|---|---|---|
| Validation (SynDD-val) | 14/15, 0.00 FA/h | 13/19, 16.05 FA/h |
| Test (SynDD-test + DAD), report only | 16/18 @1.07/h + DAD 2/2 @1.58/h = **18/20** | 13/19 @10.15/h |
| Old box detector, test | 16/18 @0/h + DAD 2/2 @8.67/h | 0/19 |

**Pi wrist check: NOT DONE.** The Pi was unreachable on all 5 hourly SSH tries (16:56–23:56).
`ncnn` is blocked by Windows Application Control on the dev PC, so models were evaluated from
PyTorch / ONNX (parity checked). Full report: [ir_report.md](ir_report.md); dataset inventory:
[dataset_inventory.md](dataset_inventory.md); change log: [ir_log.md](ir_log.md).
