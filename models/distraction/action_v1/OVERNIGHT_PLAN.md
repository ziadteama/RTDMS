# Overnight ledger (source: user's "OVERNIGHT RUN" message, 2026-11-14 ~04:00 Cairo). Stop 10:00 Cairo.

## Hard rules
H1 Phone model + weights unchanged (fusion-stage changes OK)
H2 No touching Windows Application Control / security settings
H3 No deleting data, no history rewrite, no force-push; ONE commit per iteration on branch overnight/held-object
H4 No Pi contact; no running/faking label_food.html results
H5 Never tune on test; all choices on validation; test scored only after keeping, reported only
H6 No keep/revert decision on DAD alone
H7 Bad numbers reported as is; no dropping hard clips
H8 Blocked -> log, skip, next. No questions to the user.

## Step 0 measurement
S0.1 Confirm 3MDAD/SynDD/DAD test drivers not in train/val; fix + re-score if overlap
S0.2 One rule: score ea3d6ad vs c77e01c on validation, keep better, delete other code path, 3/10/20 fps tests pass; state kept commit + why
S0.3 One FA metric: FA/h over ALL non-drinking clips (normal, hand-on-face, call, texting, smoking, yawning, talking, reaching), same for every dataset; keep per-clip-type breakdown
S0.4 DAD: add any DAD drinking clips not in training to test once, then freeze
S0.5 Small model test numbers; small = product; all decisions + headline tables use small; s = control
S0.6 Regenerate results.md baseline: small, s, old detector (eval_v2_det2); validation and test separate tables

## Step 1 missed drinks
S1.1 Each missed SynDD clip: cup not detected vs rule didn't fire (window/tilt/sip)
S1.2 Clips old detector catches but new misses + common factor
S1.3 Fix larger cause first; SynDD FA stays at/near 0
S1.4 If small clearly behind s: distillation with s soft labels; decide on validation

## Step 2 false alarms
S2.1 Fusion: no drinking while phone model says call/texting; report with + without
S2.2 Yawn veto: face-mesh mouth-open ratio threshold picked on validation
S2.3 Hard negatives: phone-in-hand + cigarette crops (train drivers only) into negative class, retrain, re-score

## Step 3 loop
S3.1 Collect val FAs + misses, group by cause
S3.2 Biggest cause -> ONE change (hard-neg mining, aug, crop size, rule window, loss weights, input res)
S3.3 Keep only if on val: recall drop <= 1 event on every dataset AND (FA/h all non-drinking down OR recall up with FA unchanged); else revert + log why
S3.4 Commit, append row to overnight_log.md (change, val before/after, kept/reverted); test scored once for kept changes
S3.5 Target recall >= 85% and <= 5 FA/h on every dataset (small). Stop: target, 3 reverts in a row, or 10:00

## Step 4 eating prep
S4.1 Hand-at-mouth crops from DAD eating clips (train drivers only), CLIP pre-sort, add + the 264 CLIP-flagged crops to label_food.html queue, most confident first
S4.2 Experimental rule eating detector: repeated hand-to-mouth + chewing (face mesh) + no cup; score on SynDD + DAD eating clips, same metrics; marked experimental

## Step 5 Pi prep (offline)
S5.1 Export best small model NCNN (no INT8), PC speed as rough guide
S5.2 Script: build INT8 on the Pi; one command for full Pi eval (IR-frame results, FPS with phone + face mesh, wrist check)
S5.3 Recording checklist: 5 clips each drinking, yawning, smoking or hand-on-face, phone use, rubbing eyes + 10 min normal driving

## Morning report (morning_report.md; also update HELD_OBJECT.md and results.md)
M1 Table: baseline vs old detector vs best overnight small, per dataset: caught/total, FA/h all non-drinking, breakdown by clip type; val and test separate; s control row
M2 Rule commit kept + why
M3 Every change tried, kept/reverted + reason
M4 Remaining failure cases with 2-3 example frames each
M5 Eating: crops waiting for labelling + experimental rule results
M6 Needs a human: blocked items + exact actions (CLIP groups + top-200 suspects check; label_food.html; Pi; ncnn2table block)
M7 Recommendation: drinking ready to switch on for Pi test, yes/no + why
