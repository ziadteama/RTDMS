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

## Method and outstanding Step0 evidence

The rule comparison tied on nano SynDD-val at11/15 and0 false drinking onsets/h;
keep c77e01c, already the sole runtime rule. s remains a control, regardless of test
scores. Historical test results are descriptive, never keep/revert evidence.

The eval_v2_det2.json artifact contains test results only. Its SynDD-val row is
BLOCKED pending replay of the exact cached detector/face streams; no test number
is substituted for validation. Original-action subtype breakdown is unavailable
from its aggregated false_alerts, so its breakdown remains true-class-level.

Clean training now excludes MDAD-val drivers10,11,15,19,50 (seed28). Training
18076 crops, combined crop-validation3375; all remaining hard negatives retained
with weighted sampling. Both clean model fits use the same split. Thresholds
will use SynDD-val plus the five driver-held-out MDAD-val scenes; tests follow
only after that validation selection is saved. Existing models' MDAD holdout
performance is contaminated and cannot decide improvements.

Live Pi drinking OFF (--no-detect). No Pi or SSH contact tonight.
The earlier old-rule3MDAD0/30 is preserved in the archived historical report;
original PhaseB loose SynDD10/18,9.7 normal+hand-on-face FA/h was worse than
release15/18,0. That9.7 is a historical denominator, not the current metric.

Artifact paths: _held_data/overnight/step0/{rule_selection,test_baseline,detector_baseline,split_freeze}.json.
