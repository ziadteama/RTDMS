# IR changes tried (2026-11-14 evening)

Keep rule (user, IR step 2.5): on IR validation (untrimmed SynDD-val), recall may drop by at most 1
event and false alarms per hour (all non-drinking clips) may not rise, versus the current best.
Base = iteration 6 nano + phone veto (val 14/15 at 1.09/h). Test scored only for kept changes.

| # | Change | IR val before → after | Decision | Reason |
|---|---|---|---|---|
| IR-1 | Camera simulation on every training crop (smaller/low-res driver, barrel distortion, blur, noise, IR tone, vignetting; RGB-sourced crops get the same tone changes) | 14/15 @1.09/h → 14/15 @3.26/h (talking 2, singing 1) | REVERTED | FA rose |
| IR-2 | Phone-in-hand hard negatives: 5,310 hand-at-mouth crops from phone call / phone-in-hand segments of 48 SynDD TRAIN drivers (cigarette negatives already present: 3MDAD smoking) | 14/15 @1.09/h → 12/15 @0.00/h | REVERTED | Recall dropped by 2 events (rule allows 1); FA fell to 0 |
| IR-3 | Phone-in-hand hard negatives, subsampled to 1,500 of the 5,310 crops (fixed seed) | 14/15 @1.09/h → 13/15 @0.00/h | **KEPT** | Recall −1 (allowed), FA down to 0. New current best. Test scored below. |

**IR-3 test (report only, untrimmed):** SynDD-test 16/18 @1.07/h (phone R 1; missed 25077_5_003, 99635_5_005), DAD 2/2 @1.58/h (normal driving 2). Combined IR drinking 18/20 = 90 %. DAD pose for frames without cached geometry came from the PyTorch pose model (ncnn blocked on this PC).
| IR-4 | Light camera simulation (p=0.3) on top of IR-3 | 13/15 @0.00/h → 14/15 @0.00/h | **KEPT** (product drinking model) | Recall +1, FA unchanged. Test (report only): SynDD 16/18 @1.07/h (missed 25077_5_003, 35418_5_008; phone R 1), DAD 2/2 @1.58/h. |

## Eating (IR step 3) — same rule for eating recall / eating FA/h

| # | Change | IR val before → after | Decision | Reason |
|---|---|---|---|---|
| E-1 | Temporal head (Linear + GRU, T = 7 samples ≈ 2.1 s, 4 classes) on the IR-3 backbone's features, run only on windows with ≥ 2 hand-at-mouth samples; event rule picked on val (thr .98, m 5) | — → 13/19 @20.63/h | baseline | An ungated first version (other-class recall 0.19) was replaced before any comparison |
| E-2 | Phone veto (no eating while the v2 phone alert is on / was on ≤ 2 s ago) | 13/19 @20.63 → 13/19 @16.05/h | **KEPT** | FA down |
| E-3 | Yawn veto (lip gap / face width > 0.15, picked on val) | 13/19 @16.05 → 14/19 @17.19/h | REVERTED | FA rose |
| E-4 | No eating while the drinking alert is on | 13/19 @16.05 → 13/19 @16.05/h | KEPT (neutral) | Rule allows equal |
| E-5 | Yawning / hand-on-head windows weighted ×3 in training | 13/19 @16.05 → 9/19 @10.32/h (after its own E-2..E-4) | REVERTED | Recall −4 |
| E-6 | Head re-trained on the IR-4 product backbone instead of IR-3 | 13/19 @16.05 → 8/19 @9.17/h | REVERTED | Recall −5 (val objective 0.24 vs 0.36): eating keeps the IR-3 backbone |

**Eating final (E-1 + E-2 + E-4, IR-3 backbone): IR val 13/19 @16.05/h; IR test (report only)
13/19 (68 %) @10.15/h** (yawning 5, drinking 1, reaching 1, singing 1, phone R 1). Target not met.
Optional noise filter (VLM + s model) not run (time); no human labels used anywhere.
