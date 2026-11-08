# action_v1 progress log

## 2026-10-26 03:17 Step 0: environment
- GPU: NVIDIA GeForce RTX 4060 Laptop, 8 GB, driver 617.42, CUDA available.
- Python 3.11.9 (existing venv C:\Users\youss\venvs\rtdms-train): torch 2.14.1+cu130, ultralytics 8.4.178,
  mediapipe 1.1.1, onnx 1.23.2, onnxruntime 1.31.0, ncnn 1.0.20260526, opencv 5.0.0, numpy 2.4.6.
- Nothing missing, so no new venv was created (see DECISIONS.md D1).
- Disk: 133 GB free on D: (budget for new files: 60 GB).
- Base weights available: yolo26n-cls.pt (classification), yolo26n-pose.pt, det_v2d release model.
- Folders created: action_v1/src, runs, splits, report_assets.
- 03:17 Step 1: FINDINGS.md written; stream.py copy reports rolling avg / per-run ms.

## 2026-10-26 Step 2: frame extraction
- Smoke test OK for syndd / 3mdad / dad. EBDD face hit rate was 1-5/21 on phone/text clips ->
  fixed with tiled face search (D8). DAD crops too dark -> contrast stretch (D9).
- Second smoke test: ebdd 297 frames 0 misses, dad drinking 51 kept / 21 no-face, 3mdad 70 / 4.
- Launching full extraction: syndd, syndd_fish, 3mdad, ebdd, dad (16 workers). 133 GB free before.
- 03:24 full extraction started (runs/extract.log). Meanwhile written: src/augment.py (lens/fisheye,
  tilt +-15 deg, brightness/contrast/gamma, blur, noise; checked on a contact sheet, toned down
  after the first version produced mirror artefacts), src/train_cls.py, src/build_cls.py,
  src/build_phone.py, src/alerts.py, src/evaluate.py, src/release_ebdd.py.
- 03:30 release model (det_v2d NCNN, simple rules) running on EBDD test videos for the
  side-by-side (runs/release_ebdd/).
- Pi (Ethernet) is disconnected right now, so step 8 Pi latency will be an estimate scaled from
  the Pi timings measured earlier (det_v2d INT8 512: ~45 ms, face mesh: ~4.4 ms per frame).
- 03:54 SynDD done: 52,125 frames kept, 3,344 skipped (no face, none held), 1,519 used a held
  face (<= 1 s old). 30 min with 16 workers. train: other 13,225, texting 6,338, call 5,354,
  hand_on_face 4,145, normal 4,037, eating 3,160, drinking 963 (drinking segments are short).
- 03:57 3MDAD done: 60,655 frames, 6,766 skipped (no face). Side labels swapped (D11).
- 03:57 release model on EBDD test: 9 videos done (akkas has no ATTENTIVE video).

## 2026-10-26 04:00 Step 3: balance (runs/balance.md)
- Extraction totals: syndd 52,125 / 3mdad 60,655 / ebdd 5,972 (84 no-face skips after D8) /
  dad 11,349 (36 skips) / syndd_fish 6,188 (530 skips). 3.3 GB on disk, 129 GB free.
- Train (SynDD-train + syndd_fish + 3MDAD-train + EBDD-train): smallest main class = eating 3,989,
  cap 3x = 11,967 -> call, texting, other subsampled. Final train: normal 8,674, call 11,967,
  texting 11,967, drinking 4,798, eating 3,989, hand_on_face 8,723, other 11,967 (62,085).
- Val (SynDD-val, same rule): drinking 148, all others 444.
- Test (natural counts): syndd normal 863 / call 1,095 / texting 1,113 / drinking 119 / eating 564 /
  hand_on_face 842 / other 2,778; 3mdad normal 1,902 / call 3,718 / texting 3,622 / drinking 3,359 /
  hand_on_face 3,880 / other 12,063; ebdd normal 293 / call 152 / texting 160 / eating 151 / other 158;
  dad normal 9,873 / call 360 / texting 429 / drinking 120 / other 567.
- 04:12 phone training try 1 failed at start: "Couldn't open shared file mapping, error 1455"
  (Windows paging file / commit memory exhausted by two trainings x 8 loader workers). The action
  run was not affected. Phone training is now chained to start when the action run ends
  (src/run_after_act.sh, up to 3 tries).
- 04:15 act_n224 early-stopped after epoch 13; best = epoch 5, SynDD-val top-1 0.655
  (train loss kept falling while val stayed 0.60-0.65 -> overfits to the training drivers).
  Frame accuracy of best.pt: SynDD-val 0.647, SynDD-test 0.667, 3MDAD-test 0.682, EBDD-test 0.409,
  DAD 0.099. Call frames: 0.94 / 0.84 / 0.77 / 0.72 (DAD IR). Weak: eating (0.20-0.56), EBDD normal
  read as eating (0.64), DAD normal driving read as other (0.66) / hand_on_face (0.28) - neither
  raises an alert, so the alert logic matters more than frame accuracy there.
- 04:20 queued the "s" size (yolo26s-cls) to train after the phone model (src/run_s.sh).
- 04:21 phone_n128 done (early stop at 16): SynDD-val ear crops top-1 0.984.

## 2026-10-26 04:25 Steps 6-7: alert logic + evaluation (v1 = act_n224 + phone_n128)
- First pass (plan rules only): recall well above release, but false alerts on normal +
  hand_on_face high (SynDD 58/h, 3MDAD 143/h, EBDD 600/h). Breakdown: call FAs rare (phone gate
  works); texting / drinking / eating FAs dominate -> probability gate per class (D12).
  Talking check never helped on SynDD-val (D13).
- With D12 (runs/eval_v1.json), ours vs release, same clips:
  SynDD-test: call 37/39 vs 34/39, texting 25/41 vs 14/41, drinking 6/18 vs 15/18, eating 1/19 vs
    0/19, FA normal+hof 14.5/h vs 0/h, phone FA on hand_on_face 0 vs 0.
  3MDAD-test (release clips: no AC12): call 30/30 vs 24/30, texting 24/30 vs 17/30, drinking
    30/30 vs 22/30, FA normal+hof 33/h vs 11/h, phone FA on hand_on_face 5.3/h vs 5.3/h.
  EBDD-test: call 1/2 vs 2/2, texting 1/2 vs 2/2, eating 2/2 vs 1/2, FA normal 270/h vs 0
    (normal read as eating; only 2 minutes of normal video, 9 onsets).
  DAD IR: call 5/5 vs 4/5, texting 4/6 vs 5/6, drinking 1/2 vs 2/2, FA normal 0/h vs 79/h.
- Remaining FAs: 3MDAD smoking -> drinking (49 on "other" clips), 3MDAD fatigue (AC12) -> drinking /
  texting, EBDD normal -> eating.
- 04:45 act_s224 (yolo26s-cls) early-stopped at 13, best val top-1 0.664 (epoch 5), same pattern
  as n. Eval v2s (same gates): SynDD FA normal+hof 38.7/h (n: 14.5), 3MDAD 81.5/h (n: 70.9),
  EBDD 120/h (n: 270), DAD texting 0/6 (n: 4/6), eating SynDD 8/19 (n: 1/19). Not better overall
  and ~3x slower -> keep the n model (v1). Gates were tuned for n; not re-tuned for s.

## 2026-10-26 04:46 Step 8: export + speed
- Exports (runs/act_n224/weights, runs/phone_n128/weights): ONNX, NCNN FP32, NCNN INT8 (KL and
  ACIQ calibration with the official ncnn tools, 600 training crops).
- Accuracy: action (3,000 SynDD-test frames) pt 0.668 / onnx 0.668 / ncnn fp32 0.668 /
  int8 KL 0.671 / int8 ACIQ 0.653. Phone (SynDD-val ears) pt 0.987 / fp32 0.987 / int8 KL 0.986 /
  ACIQ 0.984. -> INT8 KL kept for both (drop < 2 points, actually none) (D14).
- PC CPU, 4 threads, median ms: det_v2d INT8 512 20.5; action ONNX 1.6, NCNN fp32 3.1, int8 2.4;
  phone ONNX 0.8, NCNN fp32 1.1, int8 1.1.
- Pi 5 estimate (scaled from det_v2d measured 45 ms on the Pi): action int8 5.3 ms, phone int8
  2.4 ms per ear crop. Pi is unplugged tonight, so not measured on the device.

## 2026-10-26 04:55 Step 9: report
- REPORT.md written; report_assets: confusion matrices (cm_v1_*, cm_v2s_*), example crop sheets
  (examples_v1_*), hand-on-face sheets (hand_on_face_v1_syndd / 3mdad).
- Nothing under raw datasets, det_v2\ or the release model was changed (only read).

# v2 hybrid (started 2026-10-26)

## Step 1-2: lap crop for the texting phone check
- extract.py now also saves a lap crop (128 px gray; square 2.5 x face size, centred 1.25 face
  sizes below the chin) -> data/v2/<ds>.csv with a "lap" column. Existing v1 crops are not
  rewritten (they are hard-linked into data/cls). Smoke test: phone visible in 3MDAD / EBDD texting
  lap crops; DAD frames are tiny, so the crop covers most of the image.
- First runner script had a quoting bug (bash syntax error, nothing ran); fixed, re-launched.
- Release pipeline re-run on 3MDAD-test (all 15 actions incl. AC12 / AC15), EBDD-test, DAD front IR,
  this time saving box coordinates + mouth / face landmarks (src/release_run.py ->
  runs/release_v2/). SynDD uses the existing box + face caches.
- 09:10 v2 CSVs for 3mdad / ebdd / dad written; rows identical to v1 (checked crop paths + sides).
- Existing phone_n128 on lap crops (3MDAD / EBDD train drivers, texting vs normal / hof / other):
  AUC 0.50 / 0.59 -> no better than chance. Fine-tuning a lap model (src/build_lap.py, from
  phone_n128 weights) once SynDD lap crops are ready.
- v1 false alerts on 3MDAD-test by action: smoking (AC16) -> drinking 28, call 3, texting 1;
  fatigue (AC12) -> drinking 15, texting 10, call 3. In v2 drinking comes from the release
  detector, so smoking only matters for call / texting -> smoking class decided after v2 eval.
- 09:30 all v2 CSVs written (syndd 52,125 / syndd_fish 6,188, rows identical to v1).
- data/phone_lap (src/build_lap.py): train phone_in_hand 12,688 texting lap crops (syndd 6,338,
  3mdad 4,273, fish 1,257, ebdd 820), empty_hand 25,376 (other 15,889, hof 4,745, normal 4,742);
  val (SynDD-val) 1,217 / 2,434. Fine-tuning phone_lap_n128 from phone_n128 (20 epochs, 128 px).
- 09:55 phone_lap_n128 done (early stop 18): SynDD-val lap AUC 0.84 (phone_n128 on the same
  crops: 0.49). At 0.5: 49% of texting frames pass, 1.2% of others. INT8 KL export: acc@0.4
  0.823 vs 0.826 FP32.
- SynDD-val texting sweep -> lap threshold 0.4 and no texting probability gate (D19).
- Debug run of src/evaluate_v2.py on SynDD-test OK (tag dbg, ear model on the lap - ignore).

## v2 step 5: evaluation of the hybrid (runs/eval_v2.json, act_n224 + phone_n128 + phone_lap_n128)
- Release re-run done: 3MDAD-test 225 clips (all actions), EBDD-test 9, DAD 39.
- v2 vs release, FA/h on normal + hand_on_face: SynDD 0 vs 0, 3MDAD 19.6 vs 14.2, EBDD 90 vs 0
  (3 alerts in 2 min), DAD 3.6 vs 79.2. Call recall 37/39, 30/30, 1/2, 5/5 (release 34/39, 24/30,
  2/2, 4/5). Drinking back at release level (15/18, 22/30, -, 2/2).
- Remaining v2 call / texting false alerts on 3MDAD by action: smoking (AC16) 7 (4 texting,
  3 call) = largest single source -> smoking class trained (src/build_cls_v2.py, runs/balance_v2.md:
  train 2,051 smoking frames; val = SynDD-val + AC16 of 4 held-out 3MDAD train subjects).
- act_n224_smk trained (early stop 15, best val 0.657). Eval v2smk: smoking FAs 7 -> 7, all
  call / texting FAs 23 -> 28, SynDD FA/h 0 -> 14.5 -> rejected (D21); v2 = act_n224.

## v2 step 6: full-pipeline latency (runs/bench_v2_every1.json, bench_v2_every2.json)
- PC CPU (4 threads, 300 real 3MDAD frames, mean ms): det_v2d INT8 21.3, face mesh 7.4, crops 1.2,
  action 2.8, ear phone x2 2.5, lap phone 1.3 -> hybrid 37.3 ms (26.8 FPS); detector every 2nd:
  27.2 ms (36.8 FPS).
- Pi 5 estimate (CPU stages x 45 / 21.3, face mesh 4.4 measured): every frame 66 ms worst (15.1 FPS),
  60 ms typical; every 2nd 44 ms worst (22.7 FPS), 38 ms typical (26.1 FPS). -> D22.
- Re-evaluated with the detector every 2nd frame (runs/eval_v2_det2.json): see D22.

## v2 step 7: REPORT_v2.md written
- Deployable v2 = act_n224 + phone_n128 (ears) + phone_lap_n128 (lap, > 0.4) + release det_v2d
  boxes with mouth filter for drinking / eating, detector every 2nd frame on the Pi.
- Raw datasets, det_v2\ and the release model were only read. Disk: see below.
- action_v1 folder now 4.6 GB in total; 128 GB free on D:.
