# Hybrid v2 — report (2026-10-26)

## In short

v2 mixes the two earlier systems:

- **Call and texting** come from the action classifier (v1), each confirmed by a phone check.
- **Drinking and eating** come from the release detector's cup / food boxes near the mouth.

Results:

- **False alarms:** v2 removes most of v1's false alarms. It equals the release model on SynDD
  (0 per hour) and is far better on DAD IR (3.6 vs 79 per hour).
- **Recall:** v2 finds more calls and texting than release on SynDD and 3MDAD, and keeps
  release-level drinking.
- **Weak spots:** 3MDAD is still a little worse than release (19.6 vs 14.2 false alarms per hour),
  and EBDD gets 3 texting false alarms in its 2 minutes of normal driving.
- **Speed:** on the Pi 5 this needs the detector on every 2nd frame (about 23–26 FPS, estimated).

## How v2 decides

| Alert | Rule |
|---|---|
| Call | action = call in ≥ 70% of frames over 2 s, AND phone seen at an ear (ear crop model, mean prob > 0.5) |
| Texting | action = texting in ≥ 70% of frames over 1.5 s, AND phone seen in the lap crop (lap model, mean prob > 0.4) |
| Drinking / eating | release rules: drink / food box on the lower face for 0.5 s, AND box centre within 1.5 × face height of the mouth |
| Hand on face, smoking, other | never alert |

The lap crop is a fixed square under the face: 2.5 × face size, starting at the chin. It does not
use MediaPipe Hands (D16).

## Results (same clips for every system)

"x/y" = clips with a correct alert / clips of that class.
"FA/h" = false alerts per hour on normal + hand-on-face clips.
"All FA/h" = every wrong alert on every clip, per hour.
**v2 (Pi)** = detector on every 2nd frame, the setting we would deploy.

**SynDD-test** (10 drivers, 276 clips, 0.9 h)

| System | Call | Texting | Drinking | Eating | FA/h | All FA/h |
|---|---|---|---|---|---|---|
| Release | 34/39 | 14/41 | 15/18 | 0/19 | **0** | **0** |
| v1 | 37/39 | **25/41** | 6/18 | 1/19 | 14.5 | 27.3 |
| v2 | **37/39** | 18/41 | 15/18 | 0/19 | **0** | 6.8 |
| v2 (Pi) | **37/39** | 18/41 | **16/18** | 0/19 | **0** | 6.8 |

**3MDAD-test** (15 drivers, all 15 actions incl. fatigue and smoking, 225 clips, 2.8 h)

| System | Call | Texting | Drinking | FA/h | All FA/h |
|---|---|---|---|---|---|
| Release | 24/30 | 17/30 | 22/30 | **14.2** | **11.3** |
| v1 | **30/30** | **24/30** | **30/30** | 71.2 | 40.2 |
| v2 | **30/30** | **24/30** | 22/30 | 19.6 | 12.4 |
| v2 (Pi) | **30/30** | **24/30** | 25/30 | 28.5 | 17.6 |

**EBDD-test** (2 drivers, 9 videos, 6 min) — **low confidence: only 2 minutes of normal video**,
so one false alarm = 30 per hour.

| System | Call | Texting | Eating | FA/h | All FA/h |
|---|---|---|---|---|---|
| Release | 2/2 | 2/2 | 1/2 | **0** | **0** |
| v1 | 1/2 | 1/2 | 2/2 | 270 | 127 |
| v2 / v2 (Pi) | 1/2 | 1/2 | 1/2 | 90 (3 alerts) | 49 |

**DAD front IR** (3 drivers, 39 clips, 1.3 h)

| System | Call | Texting | Drinking | FA/h | All FA/h |
|---|---|---|---|---|---|
| Release | 4/5 | **5/6** | 2/2 | 79.2 | 80.9 |
| v1 | 5/5 | 4/6 | 1/2 | **0** | **0.8** |
| v2 | **5/5** | 4/6 | **2/2** | 3.6 | 3.1 |
| v2 (Pi) | **5/5** | 4/6 | **2/2** | 4.5 | 4.7 |

## Every false alarm, by (alert → true class of the clip)

| Set | Release | v2 (detector every frame) |
|---|---|---|
| SynDD | none | texting → drinking 3, texting → eating 2, texting → other 1 |
| 3MDAD | phone → other 9, phone → drinking 5, drinking → other 5, drinking → texting 4, drinking → hand_on_face 3, phone → normal 3, phone → hand_on_face 2, drinking → call 1 | call → other 6, texting → call 5, texting → other 4, drinking → other 4, drinking → texting 4, call → hand_on_face 3, texting → normal 3, drinking → hand_on_face 3, texting → hand_on_face 2, drinking → call 1 |
| EBDD | none | texting → normal 3, texting → other 2 |
| DAD | phone → normal 77, phone → other 16, drinking → normal 11 | drinking → normal 4 |

- **v2 (Pi) on 3MDAD** adds drinking → other (12 in total), drinking → hand_on_face (8) and
  drinking → texting (6).
- **v1 for reference:**
  - SynDD: texting → other 16.
  - 3MDAD: drinking → other 49, drinking → hand_on_face 17.
  - EBDD: eating → normal 8.
- **What the 3MDAD v2 alerts come from:**
  - smoking clips: 7 (4 texting, 3 call);
  - phone-to-the-ear clips: 5 texting alerts;
  - fatigue clips: 5 (3 call, 2 texting).
- **"texting → call" is harmless:** it is still phone use, just the wrong kind.

**Hand on the face, no phone:**

| Test set | v2 | Release | v1 |
|---|---|---|---|
| SynDD | 0 phone alerts | 0 | 0 |
| 3MDAD | 5 (3 call, 2 texting, all on fatigue clips) | 2 | 14 |

## What changed from v1 to v2, and why (DECISIONS.md D16–D22)

- **Lap phone check (D18, D19).**
  - The ear phone model could not read lap crops (AUC 0.49), so a lap model was fine-tuned:
    AUC 0.84 on SynDD-val.
  - The texting threshold of 0.4 was picked on SynDD-val; the plan's 0.5 gives nearly the same
    results.
  - **Effect:** texting false alarms drop a lot (SynDD 50 → 6.8 per hour all-FA; 3MDAD 31.8 →
    12.4) for some texting recall (SynDD 32 → 18 of 41 vs no check).
- **Drinking / eating from the release detector (D17).**
  - Drinking is back to release level on SynDD (15/18; v1 was 6/18).
  - The mouth filter changes nothing on SynDD or 3MDAD. On DAD it removes 7 false drinking alerts
    (9.9 → 3.6 FA/h).
- **Smoking class: tried and rejected (D20, D21).** It did not remove the smoking false alarms
  (7 → 7) and was worse elsewhere, so v2 uses the original action model.
- **Detector every 2nd frame on the Pi (D22).** See speed below.

## Speed

| | PC CPU, 4 threads | Pi 5 estimate |
|---|---|---|
| Detector every frame | 37.3 ms (27 FPS) | 66 ms worst (15.1 FPS), 60 ms typical (16.5 FPS) |
| **Detector every 2nd frame** | 27.2 ms (37 FPS) | **44 ms worst (22.7 FPS), 38 ms typical (26 FPS)** |

- **Per-stage times (PC):**

  | Stage | ms |
  |---|---|
  | Detector (det_v2d INT8, 512) | 21.3 |
  | Face mesh | 7.4 |
  | Crops | 1.2 |
  | Action model | 2.8 |
  | 2 ear checks | 2.5 |
  | Lap check | 1.3 |

- **Pi 5 estimate:** PC time × 2.1, the ratio of the detector's measured Pi time (45 ms) to its
  PC time. Face mesh uses the 4.4 ms measured on the Pi. "Typical" assumes the phone checks run on
  ~30% of frames (only while the action says call or texting).
- **Why every 2nd frame:** with the detector on every frame there is no margin above 15 FPS once
  camera capture and streaming are added. On every 2nd frame there is.
- **Cost of every 2nd frame:**
  - 3MDAD false alarms go from 19.6 to 28.5 per hour;
  - DAD from 3.6 to 4.5 per hour;
  - SynDD stays at 0;
  - drinking recall goes up.

  The 3MDAD cost is overstated: its frames are 1/3 s apart, so reusing a box covers far more time
  than at a live ~20 FPS.
- **INT8 models:** all three classifiers are exported to INT8 NCNN, losing at most 0.3 points.
- **The Pi was not connected**, so these are estimates, not measurements.

## Better / worse in one list

**Better than release:**
- call recall on every set except EBDD (SynDD 37 vs 34 of 39; 3MDAD 30 vs 24 of 30; DAD 5 vs 4
  of 5);
- texting on SynDD and 3MDAD (18 vs 14 of 41; 24 vs 17 of 30);
- DAD IR false alarms 3.6 vs 79 per hour.

**Same as release:**
- SynDD false alarms (0 per hour);
- drinking (SynDD 15/18, 3MDAD 22/30, DAD 2/2).

**Worse than release:**
- 3MDAD false alarms (19.6 vs 14.2 per hour; 28.5 with the detector on every 2nd frame);
- EBDD false alarms (3 texting alerts in 2 min of normal driving);
- EBDD call (1/2 vs 2/2) and texting (1/2 vs 2/2);
- DAD texting (4/6 vs 5/6).

**Eating:** still nearly never found on SynDD (0/19) by either system.

## Next steps

1. **Test on the Pi** with the IR camera: confirm the FPS, then run v2 and release side by side
   for 30 min of normal driving plus scripted calls, texting, drinking and hand-on-face.
2. **3MDAD fatigue / smoking → call:** require the ear phone check for longer (e.g. 3 s), or raise
   its threshold, and check the cost on SynDD-val.
3. **Lap crop:** a pose wrist point to centre the crop on the hand instead of a fixed box might
   recover texting recall (SynDD 18/41 now). Pose already exists in the release code.
4. **Eating:** no system finds it. Needs more eating data in the gray / IR look, or a dedicated
   mouth-area food model.
5. **EBDD:** its normal videos give texting false alarms (the lap model gives them 0.55 on
   average). Look at those frames before trusting the 90 per hour figure.

## Files

- **Code (`src/`):**
  - `extract.py`: adds the lap crop; CSVs in `data/v2/`.
  - `build_lap.py` + `train_cls.py`: the lap model, in `runs/phone_lap_n128/`.
  - `release_run.py`: release boxes with coordinates, in `runs/release_v2/`.
  - `alerts.py`: lap check.
  - `evaluate_v2.py`: all systems and the false-alarm breakdown.
  - `build_cls_v2.py`: smoking test.
  - `bench_v2.py`: latency.
- **Results (`runs/`):**
  - `eval_v2.json` (detector every frame, includes the ablations);
  - `eval_v2_det2.json` (every 2nd frame);
  - `eval_v2smk.json` (smoking model);
  - `bench_v2_every1.json`, `bench_v2_every2.json`.
- **Models (INT8 NCNN):**
  - `runs/act_n224/weights/best_int8kl_ncnn_model`
  - `runs/phone_n128/weights/best_int8kl_ncnn_model`
  - `runs/phone_lap_n128/weights/best_int8kl_ncnn_model`
  - plus the release `det_v2d_ir_512_det_aciq_mixed_ncnn_model`.
