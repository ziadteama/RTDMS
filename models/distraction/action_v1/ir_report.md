# IR report: drinking + eating for our IR camera (2026-11-14 → 15)

Branch `overnight/held-object`, worktree `RTDMS-held-object`. Every choice was made on IR
validation; IR test is report-only. False alarms (FA/h) = false alerts per hour over **all
non-target clips**. Windows are untrimmed for every model (the annotation itself). Product = the
small model (yolo26n-cls 128); "s" = control.

## 1. Datasets (full detail: `dataset_inventory.md`)

- **Found on D: with drinking/eating labels:**
  - **SynDD**: monochrome, NIR-sensitive daylight camera (measured colour 0.1); 69 drivers;
    3 views; drinking + eating; time-stamped.
  - **DAD**: true IR; only 3 of ~31 drivers on disk (archive part 1); drinking, no eating.
  - 3MDAD day, EBDD, AUC: RGB.
  - Drive&Act: NIR videos only, **no annotations**.
  - SynDD A2: **no released labels**.
- **Newly used:**
  - SynDD phone segments of training drivers, as 5,310 hand-at-mouth hard-negative crops
    (1,500 used).
  - All SynDD rear-view sequences, for the eating head.
- **Missing:** DAD parts 2…N, Drive&Act annotations, DMD (IR), 3MDAD night-IR + side view,
  100-Driver, State Farm. Each has its request page and what you must do in the inventory.

**IR split (`ir_split.json`, frozen, driver-disjoint):** train = SynDD 49 drivers;
**val = SynDD-val 10**; **test = SynDD-test 10 + DAD 3**. The IR test has **20 drinking and 19
eating events**, below the 30 + 30 goal, because the remaining IR data isn't on disk.

## 2. Results

### IR validation (decisions)

| Model | Drinking caught | Drinking FA/h | Eating caught | Eating FA/h |
|---|---|---|---|---|
| **Product** (drinking IR-4 + phone veto; eating head E-1+E-2+E-4) | **14/15** | **0.00** | **13/19** | **16.05** |
| Start of this run: iteration 6 + phone veto | 14/15 | 1.09 | — (no eating model) | — |
| s control (no veto) | 13/15 | 2.17 | — | — |
| Old box detector (release rules) | 13/15 | 9.78 | 0/19 | — |

### IR test (report only)

| Model | SynDD drinking | DAD drinking (true IR) | SynDD eating |
|---|---|---|---|
| **Product** | **16/18, 1.07/h** (phone at R ear 1) | **2/2, 1.58/h** (normal driving 2) | **13/19, 10.15/h** (yawning 5, drinking 1, reaching 1, singing 1, phone R 1) |
| Start of this run: iteration 6 + phone veto | 15/18, 3.21/h | 1/2, 0.79/h | — |
| s control (no veto) | 15/18, 2.14/h (talking 1, phone L 1) | 1/2, 0.00/h | — |
| Old box detector | 16/18, 0.00/h | 2/2, 8.67/h (normal driving 11) | 0/19, 0.00/h |

- **Drinking on IR test: 18/20 = 90 % at ≤ 1.6 FA/h. Meets the target** (≥ 85 %, ≤ 5/h).
- **Eating: 13/19 = 68 % at 10.15 FA/h. Does not meet it.**

**Old test sets** (from before this run, trimmed windows; not re-scored with the new models):
- iteration 6 + phone veto: 3MDAD-test 29/30 at 2.42/h;
- old detector: 3MDAD-test 22/30 at 5.24/h.

3MDAD is RGB, so it isn't part of the IR test. Why the old detector's 3MDAD figure once read
25/30 at 28.5/h: that was a different system row (the v2 hybrid) with a different FA definition.
See `results.md`.

**The 2 DAD drinking clips (starting model):** the cup **is** detected, at moderate confidence
(max 0.98 / 0.96; 29 and 41 frames > 0.5), not missed outright. Tester1 was missed because the
high scores were scattered, never sustained. The product catches both.

## 3. Every change (detail: `ir_log.md`)

| # | Change | IR val | Decision |
|---|---|---|---|
| IR-1 | Camera simulation, strong (p = 0.8) | FA 1.09 → 3.26/h | reverted |
| IR-2 | Phone hard negatives, all 5,310 | recall 14 → 12 | reverted |
| IR-3 | Phone hard negatives, 1,500 | 13/15, FA → 0 | **kept** |
| IR-4 | + camera simulation, light (p = 0.3) | 14/15, 0/h | **kept: product drinking** |
| E-1 | Eating temporal head (GRU on the small model's features, hand-at-mouth gated) | 13/19 @20.6/h | baseline |
| E-2 | Phone veto for eating | FA 20.6 → 16.1 | **kept** |
| E-3 | Yawn veto (lip/face > 0.15) | FA rose | reverted |
| E-4 | No eating during a drinking alert | unchanged | kept (neutral) |
| E-5 | Yawning windows ×3 in training | recall 13 → 9 | reverted |
| E-6 | Head on the IR-4 backbone | recall 13 → 8 | reverted: eating keeps the IR-3 backbone |

Kept from before: phone suppression at fusion, and distillation from s (both run inside the
recipe). Not done: the optional VLM + s noise filter for eating (time). I used no human labels
and no food-visible labels.

## 4. Remaining failures (frames in `report_assets/ir_fail_NN.jpg`)

| Case | What happens | Frames |
|---|---|---|
| Drinking miss, SynDD 25077 / 35418 | The hand-at-mouth gate never fires (pose / geometry), so the cup model never runs | `ir_fail_03`, `ir_fail_04` |
| Drinking FA, DAD normal driving (2) | A large hand close to the IR lens is read as a cup (0.82) | `ir_fail_01`, `ir_fail_02` |
| Drinking FA, SynDD phone at the right ear | The phone at the mouth is read as a cup; the phone alert wasn't on yet | `ir_fail_05` |
| **Eating FA, yawning (5)** | Hand at a wide-open mouth gives P(eating) = 1.0. This is the main eating error. | `ir_fail_07`, `_10`, `_15`, `_16`, `_17` |
| Eating FA, other (4) | Reaching, singing, drinking, phone | `ir_fail_06`, `_09`, `_19`, `_20` |
| Eating miss (6) | Short or hidden bites; the score never stays above 0.98 for 5 samples | `ir_fail_08`, `_11`–`_14`, `_18` |

## 5. Pi

**Not reachable:** SSH to 192.168.100.181 timed out at 16:56, 18:17, 19:17, 22:56 and 23:56.

So none of the following were done:
- INT8 build;
- FPS;
- wrist check;
- shadow mode;
- auto-labelled Pi results.

**Speed guide on this PC** (ONNX Runtime, 4 threads):
- Drinking cup model: 1.13 ms per hand-at-mouth frame.
- Eating: + 1.13 ms (its own IR-3 backbone) + 0.05 ms (head) per hand-at-mouth frame.
- At the ~18 % gate rate that's about 0.2 ms/frame on average. This is an estimate, not a Pi
  measurement.

**Ready for the Pi:** `_held_data/pi_bundle/` holds:
- the drinking ONNX, plus the eating backbone + head ONNX;
- `held_params.json`;
- the mouth fit;
- 600 calibration crops.

`pi_held/build_int8_on_pi.sh` now converts ONNX → NCNN → INT8 on the Pi, because the PC's
`ncnn` is blocked.

**Not yet done:** the eating head is exported but **not wired into `pi_held_eval.py`**, and the
shadow-mode logging is not written.

## 6. Needs a human

1. **Pi:** power it on, on the LAN at 192.168.100.181, with key SSH working.
2. **Copy the bundle:** `scp -r _held_data/pi_bundle/* khalifa@192.168.100.181:~/RTDMS/models/distraction/action_v1/pi_held/`.
3. **Run it:** `bash models/distraction/action_v1/pi_held/run_pi_eval.sh ~/rtdms_rec` (needs the
   clips from `RECORDING_CHECKLIST.md`; without clips, only the live FPS part runs).
4. **Get the missing IR data** (forms are yours to submit):
   - DAD parts 2…N (most value for drinking);
   - DMD, or Drive&Act annotations, or 100-Driver NIR (needed for eating on true IR).
5. **Windows Application Control** now blocks `ncnn` entirely on this PC. Allow it if you want
   NCNN/INT8 work here; everything else ran from PyTorch / ONNX.

## 7. Recommendation

- **Drinking: YES, ready for a live Pi test.**
  - On every IR test clip on disk it meets the target: 18/20 (90 %), ≤ 1.6 false alarms/h,
    with true-IR DAD 2/2.
  - Run it in shadow mode first, then with the buzzer.
  - Caveats:
    - SynDD is daylight monochrome, not our active-IR camera;
    - DAD is only 3 drivers;
    - Pi speed is unmeasured.
- **Eating: NO.**
  - 13/19 (68 %) at 10.2 false alarms/h on the IR test; yawning is the main error.
  - **Low confidence:** all IR eating data is SynDD daylight monochrome, and 0 true-IR drivers
    have eating clips on disk.
  - **What would fix it:** DMD or Drive&Act annotations (NIR eating with time stamps), or
    100-Driver NIR.
