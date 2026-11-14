# Morning report — held object

Snapshot 2026-11-14 04:33 Cairo.
No production phone pipeline/weights or security policy changed. Nano128 is product.

## M1 Baseline and available overnight evidence

# Overnight measurement baseline

2026-11-14. Product: yolo26n-cls 128; yolo26s-cls is control only.
FA/h everywhere below = false drinking onsets / ALL non-drinking hours. Historical normal-only FA/h in earlier documents is a different metric, not comparable.

Validation-only rule choice: `c77e01c`. No test used to choose.

## Validation

| Model | Set | Caught/total | All-negative FA/h |
|---|---|---|---|
| v2_n | SynDD-val | [11, 15] | 0.0 |
| v2_s | SynDD-val | [11, 15] | 0.0 |
| all historical models | new 3MDAD-val | NOT ELIGIBLE: trained on these drivers | pending clean retrain |

## Test (report only)

| Model | Set | Caught/total | All-negative FA/h |
|---|---|---|---|
| v2_n | syndd | [11, 18] | 4.63171437761338 |
| v2_n | 3mdad | [29, 30] | 11.693112252869605 |
| v2_n | dad | [2, 2] | 0.0 |
| v2_s | syndd | [12, 18] | 0.0 |
| v2_s | 3mdad | [30, 30] | 20.16053836701656 |
| v2_s | dad | [1, 2] | 3.9408366571371407 |
| old detector | syndd | [15, 18] | 0.0 |
| old detector | 3mdad | [22, 30] | 5.241739975424306 |
| old detector | dad | [2, 2] | 8.66984064570171 |
| live Pi --no-detect | all | 0 alerts (OFF) | 0 |

Frozen 3MDAD holdout and complete split verification: `_held_data/overnight/step0/split_freeze.json`.
Historical bug: old rule 3MDAD 0/30. Historical Phase B loose10/18,9.7 normal-only FA/h was worse than release15/18,0; retained as historical evidence, not the unified metric.
No Pi contact. No label_food results consumed. Detector subtype breakdown cannot be reconstructed from aggregated JSON alone.

### Clean leakage-free baseline (available only; not a test-selected winner)

| Dataset | Model | Caught/total | All-negative FA/h |
|---|---|---|---|

Accepted winner pointer (only explicit val-kept evidence):

```json
{}
```

## M2 Rule

Kept c77e01c on nano SynDD-val tie (11/15,0 FA/h); one production path. Coverage/sip cadence tests3/10/20fps passed25 tests.

## M3 Changes and outcomes

# Overnight iterations ? 2026-11-14

All rates use false drinking onsets / ALL non-drinking hours. Nano128 is product.

| Iteration | Change | Validation before/after | Kept/reverted | Reason |
|---|---|---|---|---|
| 0 measurement setup | Freeze driver splits, compare rule commits, unify FA denominator | Pending detached Step0 measurement | Pending | Never choose from test; new MDAD-val needs clean retraining |
| 1 clean baseline protocol | Keep c77e01c; freeze5 MDAD-val drivers; clean nano/control training | Rule comparison nano11/15,0/h for both; clean fit pending | Rule kept (tie); clean baseline training | Remove heldout contamination before later keep/revert decisions; test report only |


Job states at snapshot:

```json
[
  [
    "clean\\job.json",
    {
      "pid": 33040,
      "child_pid": 11328,
      "state": "running"
    }
  ],
  [
    "step0\\job.json",
    {
      "pid": 16948,
      "state": "done",
      "reason": "not completed"
    }
  ]
]
```

## M4 Remaining failure cases

See per-clip diagnostics under _held_data/overnight/. If example sheets are missing, they are unverified; no visual review is claimed. All hard clips retained.

## M5 Eating

Human labels not read tonight. DAD has no TRAIN drivers in current split and no eating action folder found in inspected DAD front-IR layout: DAD training queue addition blocked pending an identified eating source and authorized train-driver split. CLIP264 flagged originals remain pseudo-labels, not human results. Experimental repeated-visit/chewing results only count if an evidence file exists.

## M6 Needs a human / could not verify

Inspect provisional CLIP groups (k6),816 uncertain crops and top200 OOF suspects. Human food labelling remains separate. Pi IR wrist, labelled crop quality and concurrent FPS are BLOCKED: reachable Pi plus recorded/labelled IR clips required. No Pi/SSH contact tonight. INT8 blocked by Application Control; use an authorized target-side toolchain, never alter Windows policy. Detector original-action subtype breakdown is absent from aggregated eval_v2_det2 JSON; do not invent it.

## M7 Recommendation

No production switch-on approved. An offline/recorded Pi test is appropriate only after the nano candidate is explicitly kept on both clean validation sets, target latency/quality is measured with phone+face running, and failure sheets are reviewed. DAD2/2 alone is insufficient. Test performance never chooses the candidate.
