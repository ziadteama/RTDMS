# Overnight iterations ? 2026-11-14

All rates use false drinking onsets / ALL non-drinking hours. Nano128 is product.

| Iteration | Change | Validation before/after | Kept/reverted | Reason |
|---|---|---|---|---|
| 0 measurement setup | Freeze driver splits, compare rule commits, unify FA denominator | Pending detached Step0 measurement | Pending | Never choose from test; new MDAD-val needs clean retraining |
| 1 clean baseline protocol | Keep c77e01c; freeze5 MDAD-val drivers; clean nano/control training | Rule comparison nano11/15,0/h for both; clean fit pending | Rule kept (tie); clean baseline training | Remove heldout contamination before later keep/revert decisions; test report only |
| 2 phone veto (S2.1, fusion) | No drinking while the v2 phone pipeline's call/texting alert is on or was on in the last 2 s (same AlertLogic + thresholds as scripts/hybrid.py; phone models only run, not changed). Rule params re-picked on val. | Before: SynDD-val 10/15 @1.18/h, 3MDAD-val 9/10 @7.77/h (5 texting AC5, 1 reaching AC15). After: 10/15 @1.18/h, 9/10 @1.30/h | KEPT | FA down, no recall loss. Caveat: the action model saw the 5 frozen 3MDAD drivers in its own training, so its 3MDAD-val effect may be optimistic; SynDD-val is clean for it. Test (report only): SynDD 13/18 @3.47/h (4.63 without), 3MDAD 29/30 @3.63/h (8.47 without), DAD 1/2 @0.79/h (same). |
| 3 yawn veto (S2.2, fusion) | No drinking while face-mesh lip gap / face width > thr (thr grid .10-.40 on val, with phone veto) | Best thr .10: 10/15 @1.18/h, 9/10 @1.30/h = unchanged | REVERTED | No FA reduction on val (no yawning false alarms in either val set; the remaining ones are singing and reaching). Not scored on test. |
