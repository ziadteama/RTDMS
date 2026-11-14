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
