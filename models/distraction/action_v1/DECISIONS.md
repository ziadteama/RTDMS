# Decisions made without asking

D1. **No new venv.** Every package the plan needs is already installed in the project's training venv
    (C:\Users\youss\venvs\rtdms-train). A second copy of torch + CUDA would cost ~5 GB and give nothing.
D2. **One "call" class.** call_L / call_R are trained as a single class: EBDD calls have no side, and
    the output merges them anyway. The side is kept in the CSV.
D3. **Skipped labels:** SynDD 9/10 "pick up from floor" (often shows a real phone, earlier evaluation
    ignored it too) and 3MDAD AC9 "having picture" (phone use that is neither call nor texting).
D4. **Mapping choices:** SynDD yawning -> hand_on_face (the hand usually covers the mouth);
    SynDD singing / talking to passenger, 3MDAD singing, smoking, radio, GPS -> other.
D5. **EBDD split:** its 2 test drivers (akkas, jewel) stay test; its 2 validation drivers (aktar, asif)
    join training (only 13 drivers in total).
D6. **3MDAD split:** 35 train / 15 test subjects, seed 0 (splits/3mdad.json).
D7. **SynDD faces from the cache.** The face landmarks already cached at 10 fps for every SynDD
    video (D:/rtdms-data/eval_cache/faces/fps10, same face mesh + driver lock as the live system)
    are reused; crops are cut from the full 1920x1080 frame. No second face-mesh pass.
D8. **Tiled face search.** The face detector shrinks the whole frame to 128 px, so in EBDD (854x480,
    driver small, side window behind) it found a face in only 1-5 of 21 sampled phone/text frames. On
    a miss we now also try three overlapping tiles (60% of width, top 80% of height). EBDD phone
    frames went from 1/21 to 21/21. Same fallback is used for every dataset.
D9. **Per-crop contrast stretch** (1st-99th percentile -> 0-255) on every saved crop, and the same
    call at inference. DAD IR crops were nearly black; RGB-to-gray crops were flat.
D10. **Classifier base = yolo26n-cls** (the repo's current Ultralytics nano classifier; the plan says
    YOLO11n-cls "or similar"). yolo26 is the newer generation of the same family, same size/speed class.
D11. **3MDAD call side is mirrored.** A contact sheet showed that in 3MDAD "phone right ear" (AC7)
    the phone sits at face-mesh landmark 454 (our "left ear" crop), the opposite of SynDD. So AC7 is
    stored as side L and AC8 as side R (in our landmark convention). Only matters for picking the
    phone-side ear crop and for the per-side recall.
D12. **Probability gate per alert class.** First evaluation: call false alerts were rare (phone
    check works) but texting / drinking / eating fired on normal and hand-on-face clips. Wrong
    frames had lower confidence (median 0.5-0.7) than right ones (0.9-1.0). So each alert also
    needs the class's mean probability over its window >= MIN_P. Values chosen on SynDD-val only,
    maximising (clip recall - 0.02 x false alerts per hour on all other clips), i.e. one false
    alert per hour costs 2 recall points: texting 0.8, drinking 0.7, eating 0.7, call 0 (already
    0 false alerts on val). Test sets were not used to choose them.
D13. **Talking check off.** The lip-movement variance never added call recall on SynDD-val without
    adding false alerts (evaluate.py tune), so the call rule uses the phone crop only. The code
    path stays (AlertLogic use_talk) and is reported as a variant.
D14. **INT8 KL for deployment.** Both classifiers lose < 0.1 point with INT8 (KL calibration), well
    under the plan's 2% limit, so the INT8 NCNN models are the deployment candidates.
D15. **n over s.** yolo26s-cls was trained too (same data / recipe); it was not better on the
    test sets and is ~3x slower, so the report uses yolo26n-cls (v1).
D16. **Lap region = fixed crop under the face, not MediaPipe Hands.** Square of side 2.5 x face
    size, centred 1.25 face sizes below the chin (shifted to stay in the frame). Hands detection
    misses hands that hold a phone, and costs another model per frame on the Pi; the plan allows the
    fixed region.
D17. **Drinking / eating from the release detector.** det_v2d boxes + the release simple rules
    (drink / food box on the lower face, 0.5 s smoothing), plus a new pre-filter: the box centre
    must be within 1.5 x face height (landmark 10 to 152) of the mouth (mean of 13 / 14), using the
    last face <= 1 s old. No face -> no drink / food evidence. The action classifier is not used
    for these two alerts.
D18. **Lap phone model fine-tuned.** phone_n128 (ear crops) scored AUC 0.49 on SynDD-val lap crops,
    no better than chance, so phone_lap_n128 was fine-tuned from it on lap crops (positives =
    texting frames, negatives = normal / hand_on_face incl. fatigue / other; train drivers only):
    SynDD-val lap AUC 0.84. Two separate small models (ears, lap) on the Pi.
D19. **Texting rule v2 = action "texting" >= 70% of 1.5 s AND mean lap phone prob > 0.4; the v1
    texting probability gate (0.8) is dropped.** Chosen on SynDD-val with the D12 rule
    (recall - 0.02 x false alerts / h): lap 0.4 + no gate 22/38 at 4.1 FA/h (best), plan's 0.5
    20/38 at 2.7/h, v1 rule 24/38 at 9.6/h, no check 33/38 at 65.7/h. Plan's 0.5 is reported as
    a variant.
D20. **Smoking class added.** In v2 the smoking clips (3MDAD AC16) gave 7 of the 23 call / texting
    false alerts on 3MDAD-test, the largest single source, so act_n224_smk was trained with an 8th
    class "smoking" (never alerts; counted as "other" in frame metrics). Same drivers / splits.
    Its val smoking frames come from 4 3MDAD TRAIN subjects held out of training (SynDD has no
    smoking); 3MDAD-test is untouched.
D21. **Smoking model rejected; v2 keeps act_n224.** act_n224_smk (best val top-1 0.657 at
    epoch 7) did not remove the smoking false alerts on 3MDAD-test (7 -> 7) and was worse elsewhere:
    SynDD texting 11/41 vs 18/41 and FA/h 14.5 vs 0; 3MDAD FA/h 35.6 vs 19.6; DAD texting 1/6 vs
    4/6. Results in runs/eval_v2smk.json. One training run each, so part of the gap may be seed
    noise; it is still no gain.
D22. **Detector on every 2nd frame for the Pi.** Full hybrid with det_v2d every frame is estimated at
    66 ms / frame on the Pi 5 (15.1 FPS worst case) before camera capture and streaming, so there is
    no margin above 15 FPS. With the detector every 2nd frame (boxes reused in between, the
    pipeline's detector.every_n): 44 ms worst, ~38 ms typical (~23-26 FPS). Accuracy cost, mostly
    on 3MDAD whose stored frames are 1/3 s apart (re-used boxes stretch drink evidence a lot more
    than at a live ~20 FPS): 3MDAD FA/h 19.6 -> 28.5, DAD 3.6 -> 4.5, SynDD 0 -> 0; drinking recall
    goes up (SynDD 15 -> 16/18, 3MDAD 22 -> 25/30).
