# Action classifier v1 — overnight report (2026-10-26)

## In one paragraph

We replaced "find the phone / cup / food object" with "look at the driver's upper body and name
the action". There is one small image classifier for the action (normal, call, texting, drinking,
eating, hand_on_face, other) and one tiny classifier that checks the ear areas for a phone in the
hand. A call alert needs both: the action model says "call" for 2 s, and a phone is seen at an
ear. **Calls are now found more often than with the current release model on every test set, and
a hand on the face with no phone gave no call alert on SynDD (0 per hour) or DAD (no
hand-on-face clips there).** The weak points are eating, drinking on SynDD, and extra
texting / drinking / eating alerts on some datasets. Speed is fine: the estimate is about
60 FPS of model time on the Pi 5, well over 15 FPS.

## How it works

1. **Face mesh** finds the face. If no face is found, the last face up to 1 s old is reused;
   otherwise the frame is skipped.
2. **Upper-body crop:** a square of 2.5 × the face size, moved down to include hands and chest,
   224 px, gray, with a contrast stretch.
3. **Action model** (yolo26n-cls, 224 px) gives a probability for each of the 7 classes.
4. **Phone model** (yolo26n-cls, 128 px) looks at the two ear crops and says
   phone_in_hand or empty_hand.
5. **Alert rules** (`src/alerts.py`):
   - **Call:** "call" in at least 70% of frames over 2 s, and the average phone probability at an
     ear is above 0.5.
   - **Texting, drinking, eating:** at least 70% of frames over 1.5 s, and the class's average
     probability is at least 0.8 / 0.7 / 0.7 (chosen on SynDD-val, D12).
   - **hand_on_face** never raises an alert.

## Results — alerts (ours vs current release model, same clips)

"x/y" = clips with at least one correct alert / clips of that class.
"FA/h" = false alerts per hour on normal + hand_on_face clips (any alert type).

| Test set | Call | Texting | Drinking | Eating | FA/h normal+hand_on_face |
|---|---|---|---|---|---|
| SynDD-test (10 drivers) | **37/39** vs 34/39 | **25/41** vs 14/41 | 6/18 vs **15/18** | **1/19** vs 0/19 | 14.5 vs **0** |
| 3MDAD-test (15 drivers)* | **30/30** vs 24/30 | **24/30** vs 17/30 | **30/30** vs 22/30 | — | 33.0 vs **11.0** |
| EBDD-test (2 drivers) | 1/2 vs **2/2** | 1/2 vs **2/2** | — | **2/2** vs 1/2 | 270 vs **0** (2 min of video) |
| DAD front IR (3 drivers) | **5/5** vs 4/5 | 4/6 vs **5/6** | 1/2 vs **2/2** | — | **0** vs 79.2 |

\* The release model was not run on 3MDAD fatigue clips (AC12), so this row uses only clips that
both models have. With AC12 included, ours is 70.9 FA/h.

The release model counts any "phone" alert as a hit for both call and texting. Ours must name the
right action, which is stricter.

## Hand on the face (no phone) — the false-alarm question

| Test set | Phone alerts (call + texting) on hand_on_face clips |
|---|---|
| SynDD-test (hand on head, hair / makeup, yawning) | **0 per hour** (release 0) |
| 3MDAD-test, release clips (hair / makeup) | 5.3 / h, 1 alert (release 5.3 / h, 1 alert) |
| 3MDAD-test incl. fatigue (AC12) | 36 / h: 3 call + 11 texting alerts |

- **The phone check works for calls.**
  - Average phone probability: 0.94 on SynDD call frames, 0.04 on hand_on_face frames.
  - On DAD it removed every false call alert (13 → 0).
- **What is left is texting.** On 3MDAD fatigue clips the hands are low and in front of the
  body, which looks like texting. The phone check is not applied to texting yet (see next steps).

## Results — frame accuracy (action model alone)

| Test set | All | normal | call | texting | drinking | eating | hand_on_face | other |
|---|---|---|---|---|---|---|---|---|
| SynDD-test | 0.67 | 0.67 | **0.94** | 0.66 | 0.56 | 0.20 | **0.88** | 0.60 |
| 3MDAD-test | 0.68 | 0.45 | **0.84** | 0.72 | 0.73 | — | 0.55 | 0.69 |
| EBDD-test | 0.41 | 0.17 | 0.77 | 0.34 | — | 0.56 | — | 0.42 |
| DAD IR | 0.10 | 0.01 | 0.72 | 0.42 | 0.13 | — | — | 0.95 |

On DAD the normal-driving frames are read as "other" (66%) or "hand_on_face" (28%). Neither
raises an alert, so the low frame number there does not cause false alarms.

Confusion matrices: `report_assets/cm_v1_<set>.png`.
Example crops with the model's answer: `report_assets/examples_v1_<set>.jpg` and
`report_assets/hand_on_face_v1_<set>.jpg`.

## Speed (step 8)

| Part | PC CPU, 4 threads | Pi 5 (estimate) |
|---|---|---|
| Face mesh | — | 4.4 ms (measured on the Pi earlier) |
| Action model, INT8 NCNN, 224 px | 2.4 ms | ~5.3 ms |
| Phone model, INT8 NCNN, 128 px, × 2 ears | 2 × 1.1 ms | ~2 × 2.4 ms (only needed when "call") |
| **Total model time per frame** | | **~15 ms → ~65 FPS** |
| For comparison: release detector det_v2d INT8 512 | 20.5 ms | 45 ms (measured) |

- **How the Pi figure was estimated:** each model's PC time × (45 ms / det_v2d's PC time), with
  the same runtime (NCNN) and 4 threads. The Pi was unplugged tonight, so this is not measured on
  the device.
- **≥ 15 FPS is reachable with a wide margin,** even if the estimate is 2× too optimistic. Camera
  capture and cropping add a few ms.
- **INT8 costs nothing measurable:**
  - action model 0.671 vs 0.668 (FP32) on 3,000 SynDD-test frames;
  - phone model 0.986 vs 0.987.
- **Exported files:**
  - `runs/act_n224/weights/best_int8kl_ncnn_model`
  - `runs/phone_n128/weights/best_int8kl_ncnn_model`
  - plus ONNX and FP32 NCNN in the same folders.

## Data used

| Source | Use | Frames |
|---|---|---|
| SynDD A1 rear (49/10/10 drivers) | train / val / test | 52,125 |
| det_v2 syndd_fish | train | 6,188 |
| 3MDAD front RGB → gray (35/15 drivers, seed 0) | train / test | 60,655 |
| EBDD → gray (test: akkas, jewel) | train / test | 5,972 |
| DAD part 1 front IR | test only | 11,349 |
| Open Images, DMS_Project v2, ADMS_FINAL_3, det_v2 phone boxes | phone model | 9,626 phone crops |

- **Sampling:** 2.5 frames per second, with 0.5 s dropped at each segment edge.
- **Balancing:** no training class is more than 3× the smallest main class (eating, 3,989).
  Final training set: 62,085 crops (`runs/balance.md`).
- **Label mapping:** `class_map.json`.

## What failed or went wrong

- **EBDD faces were missed:** the face detector found a face in only 1–5 of 21 frames. Fixed by
  also searching three overlapping tiles (D8); now 84 frames are skipped out of about 6,000.
- **DAD IR crops were nearly black.** Fixed with a per-crop contrast stretch (D9), which is also
  applied at run time.
- **3MDAD call sides are mirrored** compared to SynDD. Fixed in the labels (D11).
- **Two training crashes, both on the Windows side:**
  - pinned memory error → loaders now run without pinned memory;
  - out of commit memory when two trainings ran at once → the runs were made sequential.
- **The talking (lip movement) check never added recall** on SynDD-val, so it is off (D13). The
  code is kept.
- **Overfitting:**
  - the action model peaks at epoch 5 (val top-1 0.655), then only memorises the training
    drivers;
  - the larger "s" model behaved the same and was not better (D15).
- **Weak classes:**
  - eating (0.20 frame accuracy on SynDD; it looks like normal / texting);
  - drinking on SynDD (6/18 clips; only 963 SynDD training frames);
  - 3MDAD smoking is read as drinking (49 extra drinking alerts on "other" clips);
  - EBDD normal is read as eating.

## Next steps (in order)

1. **Use the phone check for texting too.** Run the phone model on a lap / hands crop, and use it
   to block texting alerts when no phone is seen. This is the main source of hand-on-face and
   normal false alarms left.
2. **Add smoking as its own class** (3MDAD AC16) so that it stops looking like drinking. Add more
   drinking examples from SynDD (repeat the short drinking segments).
3. **Run on the Pi** with the INT8 models to confirm the speed estimate. Then run a side-by-side
   live test against det_v2d on the IR camera.
4. **Make the models generalise better:** stronger augmentation or label smoothing, fewer epochs,
   or a short-clip temporal model over 2–3 s of crops instead of single frames.
5. **Check that the probability gates (D12) hold on another validation set**, e.g. a few 3MDAD
   training drivers held out. They were chosen on SynDD-val only.

## Files

- **Code:** `src/`
  - `extract.py`: step 2;
  - `build_cls.py`: step 3;
  - `train_cls.py` + `augment.py`: step 4;
  - `build_phone.py`: step 5;
  - `alerts.py`: step 6;
  - `evaluate.py` + `release_ebdd.py`: step 7;
  - `bench.py`: step 8;
  - `examples.py`: report pictures.
- **Results:**
  - `runs/eval_v1.json` (all numbers above);
  - `runs/eval_v2s.json` (s model);
  - `runs/bench.json`.
- **Notes:** `PROGRESS.md` (timeline), `DECISIONS.md` (D1–D15), `FINDINGS.md` (step 1: why
  detect / pose showed 0 ms).
