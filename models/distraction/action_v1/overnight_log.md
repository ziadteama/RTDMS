# Overnight iterations ? 2026-11-14

All rates use false drinking onsets / ALL non-drinking hours. Nano128 is product.

| Iteration | Change | Validation before/after | Kept/reverted | Reason |
|---|---|---|---|---|
| 0 measurement setup | Freeze driver splits, compare rule commits, unify FA denominator | Pending detached Step0 measurement | Pending | Never choose from test; new MDAD-val needs clean retraining |
| 1 clean baseline protocol | Keep c77e01c; freeze5 MDAD-val drivers; clean nano/control training | Rule comparison nano11/15,0/h for both; clean fit pending | Rule kept (tie); clean baseline training | Remove heldout contamination before later keep/revert decisions; test report only |
