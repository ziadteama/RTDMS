# Held-object drinking — results

2026-11-14 (overnight run, branch overnight/held-object). Dataset version: held_object_v2
(manifest sha256 93f34932...; split freeze in `_held_data/overnight/step0/split_freeze.json`).
Product model: distilled nano (`_held_data/overnight/distill/weights/best.pt`, FP32 NCNN
`best_ncnn_model`; INT8 not built, see below). Rule: c77e01c, params p=0.9, x=5, window=0.3,
loose gate h=0.35 / K=1.25, phone call/texting veto at fusion.
FA/h = false drinking alerts per hour over ALL non-drinking clips. Choices on validation only;
test is report-only. Full narrative, failure cases and needs-a-human list: `morning_report.md`.
Earlier versions of this file (normal-only FA/h, pre-fix 3MDAD 0/30) are superseded.

## Drinking results (validation and test separate)

### Validation (used for the decisions)

| Model | SynDD-val caught | SynDD-val FA/h | 3MDAD-val caught | 3MDAD-val FA/h |
|---|---|---|---|---|
| Baseline: clean nano, no veto (iteration 1) | 10/15 | 1.18 (singing 1) | 9/10 | 7.77 (texting 5, reaching 1) |
| **Best overnight: distilled nano + phone veto** | **10/15** | **0.00** | **9/10** | **0.00** |
| s control, clean, no veto | 13/15 | 2.35 | 9/10 | 16.84 |
| Old box detector (eval_v2_det2 replay) | 13/15 | 10.59 (eating 5, phone 2, reaching 1, yawning 1) | n/a (no replay on these drivers) | n/a |

### Test (report only, never used to choose)

| Model | SynDD-test | 3MDAD-test | DAD (real IR) |
|---|---|---|---|
| Baseline: clean nano, no veto | 13/18, 4.63/h (talking 2, yawning 1, phone at ear 1) | 29/30, 8.47/h (texting R 11, phone L 4, phone R 2, smoking 1, singing 1, GPS 1, texting L 1) | 1/2, 0.79/h |
| Clean nano + phone veto (iteration 2) | 13/18, 3.47/h (talking 2, yawning 1) | 29/30, 3.63/h | 1/2, 0.79/h |
| **Best overnight: distilled nano + phone veto** | **12/18, 0.00/h** | **29/30, 2.42/h** (smoking 3, singing 1, texting R 1, phone L 1) | **0/2, 0.00/h** |
| s control, clean, no veto | 14/18, 2.32/h | 30/30, 13.31/h | 1/2, 0.00/h |
| Old box detector (eval_v2_det2) | 15/18, 0.00/h | 22/30, 5.24/h | 2/2, 8.67/h |
| Live Pi today (`--no-detect`) | drinking OFF | OFF | OFF |

**Target (≥ 85 % recall and ≤ 5 FA/h on every dataset, nano): NOT reached.**
- **3MDAD:** meets the target (97 %, 2.4/h).
- **SynDD:** 67 % recall, below target; false alarms meet it.
- **DAD:** 0/2. That is only two clips, but it's still a miss on real IR.

**Measurement finding (does not change any decision):** SynDD event windows are the annotation
**trimmed by 0.5 s at each end** (`phase_b.windows`, a crop-label choice). Alerts that start in
the first half-second of a sip therefore score as misses. Re-scoring with the untrimmed
annotation (`_held_data/overnight/boundary.json`):

| Distilled nano + phone veto | Trimmed (official) | Untrimmed |
|---|---|---|
| SynDD-val | 10/15, 0/h | 11/15, 0/h |
| SynDD-test | 12/18, 0/h | 16/18, 0/h |

The old detector was also scored on trimmed windows (evaluate_v2 "minus 0.5 s edges"), so the
fair comparison stays **12/18 vs 15/18**. Re-scoring both sides untrimmed needs the old
detector's per-event times, which the saved JSON doesn't have. Fixing the window definition is a
decision for you.

