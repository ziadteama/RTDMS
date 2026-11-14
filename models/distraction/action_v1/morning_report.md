# Morning report: held-object drinking / eating (overnight 2026-11-14)

Branch `overnight/held-object` (worktree `RTDMS-held-object`). Product = small model
(yolo26n-cls 128, "nano"); the s model is a control row only. **Every choice was made on
validation; test numbers are report-only.** False alarms are counted per hour over **all
non-drinking clips** (normal, hand on face, phone, texting, smoking, yawning, talking, reaching,
and so on), with the same metric on every dataset.

Validation = SynDD-val (10 drivers) + 3MDAD-val (5 TRAIN drivers frozen tonight: s10, s11, s15,
s19, s50, removed from all overnight training). Test = SynDD-test (10 drivers), 3MDAD-test
(15), DAD real IR (3 drivers, only **2 drinking clips**, so one clip is 50 points).

Who did what: Codex did Step 0 and iteration 1 (commits d4935be, 251d78d), then stopped
answering after 05:13. Its MCP thread had grown to ~29M tokens and the bridge never ran a
fresh thread. I (Claude) did everything after that myself.

## M1. Results

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

## M2. Rule kept

**c77e01c**, chosen on SynDD-val by Codex in Step 0 (a tie with ea3d6ad; the tie kept the
current rule). The fps tests (3/10/20 fps, 25 tests) pass on it. ea3d6ad's path is not kept as
an alternative.

## M3. Every change tried

| # | Change | Validation before → after | Decision |
|---|---|---|---|
| 0 | Measurement contract: frozen splits, one rule, one FA metric | n/a | Done (Codex) |
| 1 | Clean retrain without the frozen 3MDAD-val drivers | baseline: 10/15 @1.18; 9/10 @7.77 | Baseline (Codex) |
| 2 | Phone call/texting veto at fusion (S2.1) | 3MDAD-val 7.77 → 1.30/h, recall same | **KEPT** |
| 3 | Yawn veto, lip gap / face width > thr (S2.2) | no change at any threshold (no yawning FAs in val) | REVERTED |
| 4 | Distil s into nano (S1.4) | FA 1.18/1.30 → 0/0, recall same | **KEPT** |
| 5 | Dataset × class sampling, plain CE | SynDD 10 → 13/15, but 3MDAD FA 0 → 9.07/h | REVERTED |
| 6 | Distillation + dataset × class sampling | ITER6_VAL | ITER6_DECISION |
| S2.3 | Phone + cigarette hard negatives | not run | **SKIPPED**: cigarette crops (3MDAD smoking) are already negatives. The phone clips of training drivers have no hand/face geometry; building it needs a new pose + face-mesh pass. The phone veto (kept) already removes most phone false alarms. |

Details per row in `overnight_log.md`.

## M4. Remaining failure cases (validation, best model; frames in report_assets/)

| Case | What happens | Frames |
|---|---|---|
| SynDD 61962 (two short sips) | Small paper cup almost hidden in the hand; cup score 0.07–0.11 | `overnight_fail_04.jpg`, `overnight_fail_05.jpg` |
| SynDD 47457 | Cup score never above threshold (the old detector missed it too) | `overnight_fail_03.jpg` |
| SynDD 84935 | Cup seen at 0.99, the alert fires at 428.2 s, but the trimmed window starts at 428.5 s (the boundary finding above) | `overnight_fail_06.jpg` |
| SynDD 16700 | 1.1 s sip, only 3 frames above threshold, so the rule needs more | `overnight_fail_02.jpg` |
| 3MDAD S10 AC14 (left-hand drink) | Hand at mouth on only 16/95 frames; cup score ≤ 0.25 | `overnight_fail_01.jpg` |

Remaining test false alarms (distilled + veto) are on 3MDAD only: smoking 3, singing 1, one
texting and one phone call that the veto didn't catch.

## M5. Eating

- **Waiting for labels:** 1,161 crops in the new queue `_held_data/label_food_v2.html`:
  - 264 that CLIP says show food, most confident first;
  - 816 uncertain;
  - 81 that CLIP says show an empty hand.
  
  The v1 page is unchanged. There are 0 DAD crops, because DAD's drivers are all test drivers.
- **No eating model trained:** fewer than 300 hand-checked food crops exist.
- **Experimental eating rule** (hand-to-mouth visits with no cup + chewing; validation-picked):
  - SynDD-val: 3/19 caught, 8.7 FA/h.
  - SynDD-test: 0/19 caught, 8.6 FA/h.
  - **Not usable**, as before (rule B).

## M6. Needs a human

1. **Pi:** `192.168.100.181` was unreachable earlier; I didn't try tonight (rule H4). Power it
   on, then:
   1. On the PC: `python models/distraction/action_v1/pi_held/prepare_pi_bundle.py <model dir> <params json>`, then `scp` the bundle.
   2. Record the test set (`pi_held/RECORDING_CHECKLIST.md`).
   3. On the Pi: `bash models/distraction/action_v1/pi_held/run_pi_eval.sh ~/rtdms_rec`. It
      builds INT8 on the Pi, reports drinking results on IR frames, measures FPS with the phone
      model and face mesh running, and makes the wrist-check sheet.
   
   These scripts were written offline and have **never been run**.
2. **INT8 on this PC:** Windows Application Control blocks `ncnn2table.exe`. Either allow it
   yourself, or use the Pi build script above.
3. **Labels:** run `label_food_v2.html` (eating needs at least 300 hand-checked food crops from
   at least 3 drivers). Also check the CLIP groups and the top-200 suspect crops in
   `held_object_v2/sheets/` (no relabelling was done automatically).
4. **Decide the SynDD scoring window** (trimmed vs untrimmed annotation; see M1).
5. Codex is unresponsive. It needs a restart of the Codex MCP bridge (`codex_bridge.py`)
   before it can be used again.

## M7. Recommendation

**Drinking is ready for a Pi test in shadow mode (logging only, no buzzer), not ready to switch
on as a live alert.**

- **Why test it now:**
  - The best small model has very few false alarms: 0/h on SynDD and DAD, 2.4/h on 3MDAD,
    against the old detector's 5.2 and 8.7/h.
  - 3MDAD recall is high: 29/30.
  - The open question is our real IR camera at the mirror, and only Pi recordings can answer it.
- **Why not live:**
  - SynDD recall is 12/18 (16/18 with untrimmed windows), below the old detector's 15/18.
  - DAD (real IR) is 0/2.
  - Speed is unmeasured on the Pi. My PC estimate: pose every 3rd frame ≈ 6 ms/frame plus the
    cup model 1.4 ms when the hand is at the mouth, about 13 ms/frame on a Pi 5 (×2.1). That's
    above the 10 ms target and is an estimate, not a measurement.
