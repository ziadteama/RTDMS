# Held-object drinking — results

2026-11-14 (overnight run, branch overnight/held-object). Dataset version: held_object_v2
(manifest sha256 93f34932...; split freeze in `_held_data/overnight/step0/split_freeze.json`).
Product model: overnight iteration 6 nano (`_held_data/overnight/distill_rw/weights/best.pt`,
FP32 NCNN `best_ncnn_model`; INT8 not built). Rule c77e01c, p=0.9, x=5, window=0.5, loose gate
h=0.35 / K=1.25, phone call/texting veto at fusion (`pi_held/held_params.json`).
FA/h = false drinking alerts per hour over ALL non-drinking clips. Choices on validation only;
test is report-only. Narrative, failure cases and needs-a-human list: `morning_report.md`.
Earlier versions of this file (normal-only FA/h, pre-fix 3MDAD 0/30) are superseded.

## Drinking results (validation and test separate)

### Validation (used for the decisions)

| Model | SynDD-val caught | SynDD-val FA/h | 3MDAD-val caught | 3MDAD-val FA/h |
|---|---|---|---|---|
| Baseline: clean nano, no veto (iteration 1) | 10/15 | 1.18 (singing 1) | 9/10 | 7.77 (texting 5, reaching 1) |
| Distilled nano + phone veto (iteration 4) | 10/15 | 0.00 | 9/10 | 0.00 |
| **Best overnight: iteration 6 (distillation + dataset × class sampling) + phone veto** | **11/15** | **0.00** | **9/10** | **0.00** |
| s control, clean, no veto | 13/15 | 2.35 | 9/10 | 16.84 |
| Old box detector (eval_v2_det2 replay) | 13/15 | 10.59 (eating 5, phone 2, reaching 1, yawning 1) | n/a (no replay on these drivers) | n/a |

### Test (report only, never used to choose)

| Model | SynDD-test | 3MDAD-test | DAD (real IR) |
|---|---|---|---|
| Baseline: clean nano, no veto | 13/18, 4.63/h (talking 2, yawning 1, phone at ear 1) | 29/30, 8.47/h (texting R 11, phone L 4, phone R 2, smoking 1, singing 1, GPS 1, texting L 1) | 1/2, 0.79/h |
| Clean nano + phone veto (iteration 2) | 13/18, 3.47/h (talking 2, yawning 1) | 29/30, 3.63/h | 1/2, 0.79/h |
| Distilled nano + phone veto (iteration 4) | 12/18, 0.00/h | 29/30, 2.42/h (smoking 3, singing 1, texting R 1, phone L 1) | 0/2, 0.00/h |
| **Best overnight: iteration 6 + phone veto** | **12/18, 0.00/h** | **29/30, 2.42/h** (smoking 2, singing 1, texting R 1, texting L 1, phone L 1) | **0/2, 0.00/h** |
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

| Best (iteration 6) + phone veto | Trimmed (official) | Untrimmed |
|---|---|---|
| SynDD-val | 11/15, 0/h | 11/15, 0/h |
| SynDD-test | 12/18, 0/h | 16/18, 0/h |

The old detector was also scored on trimmed windows (evaluate_v2 "minus 0.5 s edges"), so the
fair comparison stays **12/18 vs 15/18**. Re-scoring both sides untrimmed needs the old
detector's per-event times, which the saved JSON doesn't have. Fixing the window definition is a
decision for you.


---

## IR evaluation (2026-11-14 evening) — supersedes the tables above for decisions

**IR split (frozen, `ir_split.json`, driver-disjoint):**
- train: SynDD train drivers (49);
- **IR validation:** SynDD-val (10 drivers, rear view);
- **IR test:** SynDD-test (10 drivers, rear view) + DAD Tester1/10/11 (front IR).

Two caveats:
- SynDD is a monochrome daylight camera (measured colour 0.1), not active IR. DAD is true IR.
- **Event counts are below the 30 + 30 goal:** IR test drinking = 18 + 2 = **20**, eating =
  19 + 0 = **19** (DAD has no eating). The extra IR data is not on disk; see
  `dataset_inventory.md`.

**Scoring:**
- **Untrimmed windows** for every model and the old detector. SynDD windows = the annotation;
  the earlier tables used the annotation minus 0.5 s per side.
- One false-alarm rate: false alerts per hour over all non-target clips.
- Rule parameters of each of our models re-picked on IR validation only.

### Drinking — IR validation

| Model | Caught | FA/h | False alarms by clip type |
|---|---|---|---|
| Best small (iteration 6 + phone veto), p=.5 x=15 w=.3 | 14/15 | 1.09 | — |
| Clean small, no veto | 12/15 | 6.52 | — |
| s control, no veto | 13/15 | 2.17 | — |
| Old box detector (release rules, fixed) | 13/15 | 9.78 | — |

### Drinking — IR test (report only)

| Model | SynDD-test | DAD (IR) | False alarms by clip type |
|---|---|---|---|
| Best small (iteration 6 + phone veto) | 15/18, 3.21/h | 1/2, 0.79/h | SynDD: phone at right ear 3; DAD: normal driving 1 |
| Clean small, no veto | 14/18, 9.62/h | 2/2, 1.58/h | SynDD: phone R 5, talking 2, yawning 2; DAD: normal 2 |
| s control, no veto | 15/18, 2.14/h | 1/2, 0/h | SynDD: talking 1, phone L 1 |
| Old box detector | 16/18, 0/h | 2/2, 8.67/h | DAD: normal driving 11 |

**Eating, IR test:** the old box detector catches **0/19** on SynDD-test (0/19 on val). No
eating model of ours existed before step 3.

**The 2 DAD drinking clips:** the cup **is** detected, at moderate confidence. That's not a
case of the cup not being seen.

| Clip | Hand at mouth | Max cup score | Frames > 0.5 | Frames > 0.9 | Best small |
|---|---|---|---|---|---|
| Tester10 | 78 of 338 frames | 0.976 | 29 | 6 | caught |
| Tester1 | 245 of 338 frames | 0.959 | 41 | 1 | **missed**: high-scoring frames are scattered, never sustained enough for the rule |

### Why the old detector's 3MDAD numbers changed between runs (25/30 at 28.5/h → 22/30 at 5.2/h)

They are two different systems measured two different ways. Both come from the same file
(`D:\rtdms-data\action_v1\runs\eval_v2_det2.json`, 3MDAD-test):
- **25/30 at 28.5/h:** the **v2 hybrid** (action classifier + release detector for drinking,
  detector on every 2nd frame). Drinking recall was 25/30. Its false-alarm rate counted **every
  alert type** (call + texting + drinking) on **normal + hand-on-face clips only** (16 alerts in
  0.562 h).
- **22/30 at 5.2/h:** the **release box detector alone**. Drinking recall was 22/30. Its
  false-alarm rate counts **only drinking alerts** over **all non-drinking clips** (the unified
  metric from 2026-11-14). The same row's old-style number is 14.2/h (all release alerts on
  normal + hand-on-face).

So neither the detector nor the data changed; the system row and the false-alarm definition did.
