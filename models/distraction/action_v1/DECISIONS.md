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

D23. **Held-object Phase A remains partial (2026-11-08).** The existing Python launcher cannot
    execute its base interpreter (Access is denied), so a read-only PowerShell/.NET audit of
    the supplied SynDD rich cache was used. It covers 40 val/test videos; 98 training video
    blocks lack rich pose caches. The cache generator used PyTorch pose, not the deployed NCNN
    export; these numbers are geometry coverage, not localization accuracy or NCNN parity.
    No crops/sheets/inference/training ran. See HELD_OBJECT.md for actual counts and blockers.
D24. **Provisional held crop: K=1.0, side=2.0 face heights, midpoint of wrist and mouth.**
    On SynDD-val, K=.75 / 1 / 1.5 admits 5.29 / 45.74 / 76.18% of drinking frames and
    0 / 3.54 / 26.73% of normal frames. K=1 is the starting compromise, pending image review,
    not a validated final threshold. Face height is Euclidean landmark 10-152; mouth is mean
    13/14; confident wrist means >=0.3 as in release. Gray 128px crops use D9 normalization.
D25. **Held-object weak labels retain original driver splits and explicit negative labels.**
    New preparation scripts accept drinking/eating only with wrist geometry, and normal,
    hand_on_face, talk/sing/yawn plus 3MDAD fatigue and smoking as negatives. They do not map
    all of "other" to empty_hand. Test geometry may be audited, but the crop builder excludes
    all test records; only SynDD-val tunes. Nothing was trained. These scripts are statically
    checked only; the build and human contact-sheet check remain open. Git commits were also
    blocked by the read-only parent worktree index, and no permission workaround was attempted.

D26. **A wrist is below a held bottle, not at the mouth (2026-11-14 review).** On the DAD
    real-IR sheet the bottle reaches the mouth while the wrist/forearm can sit 1.5-2 face
    heights lower; the original K=1 wrist gate passes only 34/664 drinking frames. Face mesh
    is also lost behind the bottle. Therefore the crop build is on hold. A cache-only geometry
    job tests hand = wrist + h*(wrist-elbow), h in {0, .35, .5}, with elbow confidence >=.3
    and wrist fallback when the elbow is missing. Mouth priority is current mesh, last mesh
    <=1 second old, then a pose-head regression fitted only on SynDD TRAIN. Both c and the
    inter-eye/eye-to-ear height scales g use face-height-normalized least squares; internal
    held-out TRAIN drivers choose the height scale and provide fit-error evidence.
    The first grid review used the orchestrator's proposed normal-rate limits (<=2% on
    SynDD-val, <=5% on 3MDAD/EBDD train). The orchestrator subsequently corrected that
    criterion: normal proximity supplies valid empty_hand hard negatives and determines
    runtime classifier cost, not label noise. Those limits were wrong for constructing
    labels; the historical grid remains evidence, but D27 replaces parameter selection.
    Test/DAD rows remain descriptive only. EBDD train normal was 548/7140 at original K=1.
    New crop geometry is
    midpoint of mouth/hand, side=max(2 face heights, 1.3*mouth-hand distance). Larger 512px
    review tiles show wrist, projected hand, source-coloured mouth, K circle and crop square,
    including DAD mesh-lost drinking frames. All full COCO keypoints are already cached;
    no inference, crop build or training is authorized in this correction job. Original audit
    files remain intact; corrected outputs go under ignored `_held_data/geometry_v2/`.

D27. **Build a loose corpus and retain gate distances (2026-11-14).** Use h=.35, K=1.25,
    with D26's mesh -> held <=1s -> pose-mouth fallback and covering square. Do not choose a
    single tight runtime gate now. Only train drivers and SynDD-val produce crops; no test
    crops or training. Save both h=0 and h=.35 distances, face source, original action label,
    driver/split/clip/time and wrist/elbow confidences. Tight is selectable as dist_h0<=1
    within the same saved loose corpus; report the count of h=0 tight frames outside the
    loose gate rather than silently adding them. Greedy chronological thinning enforces
    >=.3 seconds between retained crops per clip; report before/after counts. The square
    keeps its centre and covers mouth and hand, with replicate padding outside the frame,
    128px gray AREA resize and D9 contrast stretch. Record padding in the manifest.
    Write loose/tight balance and original-label negative breakdowns, and separate train/val,
    class and tight/loose-only random sheets (seed 27; at most 48 samples; 192px crop tiles).
    Positive crops with no visible object remain the weak-label risk requiring review.
    Phase B may compare subsets on SynDD-val; no classifier is trained in this build.

D28. **Phase B is drinking only (2026-11-14, user approved).** Sheet review found roughly
    46/48 tight cup samples usable and appropriate empty_hand hard negatives, but only about
    7/48 food samples visibly contained food. Food is excluded from BOTH classifier classes,
    not reassigned to empty_hand. The team's label_food.html and food_labels.csv are protected
    and never modified. Train tight and loose binary nano classifiers initially; cap each train
    driver/class at 100 crops, cap each dataset to at most the other datasets combined when
    possible, then balance the two train classes. Keep SynDD-val uncapped for evaluation.
D29. **Freeze drinking selection before opening test results.** Compare available-backend crop AUC and
    gated alert-level D12 objective on SynDD-val only. Pose is updated every third sampled
    frame and its arm/head points held between updates; classifier runs only near the mouth.
    Tight gate h=0/K=1 and loose h=.35/K=1.25 use D26 mouth fallback. Both training subsets
    use stored h=.35 crop pixels; tight runtime crops use h=0, an explicit geometry difference
    measured on val. Tune P, pitch-up X and averaging window on val; never test. Empty-hand
    top probability cannot alert. A sustained mean-cup condition needs .5s unless pitch-up
    qualifies relative to the driver's prior non-near running pitch baseline.
D30. **Phase B artifacts stay local; no Phase C wiring.** Train recipe follows train_cls.py,
    export FP32 and KL INT8, and name the chosen local export held_cup_n128. Test predictions
    use transient in-memory crops and the evaluate_v2 clip universes (276 SynDD, 225 3MDAD,
    39 DAD), including reaching, smoking and fatigue. Legacy mouth models map P(drink) to
    cup and run with the same chosen rule. Their original mouth-crop training domain differs
    from the held-hand crop. PC pose/crop timing uses four threads; Pi timing is explicitly
    an estimate at x2.1. Initial LAN key-auth probe timed out; benchmark stage retries.
    No hybrid.py, stream.py, Pi start script, call/texting or eating implementation changes.

D31. **Application Control is a hard export boundary (2026-11-14).** ncnn2table.exe
    failed with WinError 4551. INT8 remains open, not a prerequisite for evaluation.
    Do not retry the known-blocked tool, alter policy, or copy/rename/replace executables.
    Reuse the trained tight checkpoint and completed FP32 NCNN export. Export subsequent
    variants to FP32 NCNN; if unavailable, use the same checkpoint on CPU with direct
    128px gray-to-three-channel /255 tensors (no additional contrast stretch). Record the
    backend explicitly in metrics and latency. B3 is partial; Pi is open after LAN timeout.
D32. **Compare a driver-only cap without discarding negative diversity (2026-11-14).**
    Add tight_drv alongside the original tight/loose variants. Retain at most 60 crops
    per train driver/class, with no dataset equalisation or class downsampling. Use
    inverse-class-frequency weighted sampling with replacement, one retained-set-length
    epoch, seed 28. The cap applies to distinct retained crops; sampling may repeat them.
    Validation is uncapped and unweighted. Choose among all three variants using only
    SynDD-val alert objective and crop AUC; no test-set threshold or variant selection.

D33. **Versioned v2 evidence, original labels retained (2026-11-14).** User supersedes the
    remaining Phase B plan. Preserve completed phaseB outputs as the old-label baseline.
    Use local cached CLIP ViT-L/14 only; exact two requested prompts. Candidate spherical
    k-means k=2,3,4,6,8 partitions and contact sheets support visual review. Numerical
    cosine-silhouette selection is provisional, explicitly not claimed as visual inspection.
    Pseudo-label confidence requires softmax>=.6, absolute cosine margin>=.015 and agreeing
    cluster median margin of at least .015. Cluster evidence is correlated with zero-shot
    evidence, not independent verification. All uncertain sheets retained; no auto-resolution.
    Five driver-disjoint OOF fits use at most15 epochs; NumPy confident-joint diagnostic
    uses mean class self-confidence thresholds and ranks by self-confidence. Suspects are
    never automatically relabelled. Binary training retains ALL original binary crops,
    including 3MDAD negatives, balanced sampling without driver/dataset caps; ALL original
    food stays excluded, including CLIP-empty. Local nano and small controls, SynDD-val-only
    rule/model selection, original tests isolated. Additional augmentation: low-light gain
    [.25,.75] p=.35 and scale [.65,1.25] p=.4 on top of documented CropAug. No downloads,
    package installs, policy/executable changes, runtime edits, or data deletions.
    Pi and labelled Pi IR evaluation are blocked. Human food CSV is absent at launch.
    Three-class training remains gated on >=300 human food crops from >=3 drivers.

D34. **Cadence is part of drinking-rule timing (2026-11-14).** The orchestrator found
    that a .3s SynDD-val window drops the previous sample at 3fps, preventing coverage
    and producing historical 3MDAD-test 0/30 despite high cup scores. This is an algorithm
    defect, not classifier evidence. The correction is decided from frame-spacing
    reasoning, not optimized on test scores. Effective window=max(configured window,
    2.5*stream median interval), median over the last15 positive gaps<=1s. Coverage is
    >=2 eligible samples OR >=.8*effective-window span. Sip requires >=2 consecutive
    confirmed samples and span>=max(dt,.5-.5*dt) seconds: nearest-frame quantisation,
    at 3fps two confirmations 1/3s apart; at 10/20fps observed confirmed span .5s.
    Empty/low-cup or >1s gap resets confirmation. Tests cover 3/10/20fps, one onset
    for sustained cup, none for empty, brief blips, exact onset timing and interruption.
    Re-select Phase B loose thresholds and v2 model/thresholds on SynDD-val only, then
    score tests once with locked choices. Keep old-rule metrics and outputs intact;
    corrected artifacts in _held_data/rule_d34. v2 reloads the rule before evaluation.
    Existing v2train finished before this review; detached rulefix rechecks its cached
    evidence, running new test inference only if a different val-selected model needs it.
    Live Pi drinking remains OFF; historical Phase B loose10/18 and9.7 FA/h is worse
    than release15/18 and0 FA/h. Do not erase or reinterpret those historical numbers.

D35. **Overnight measurement contract (2026-11-14).** Follow OVERNIGHT_PLAN H1-H8.
    Nano yolo26n-cls128 is the product; s is a control and cannot choose the product
    rule. ONE FA metric: false drinking onsets / hours of ALL non-drinking clips,
    with original-action breakdown where source data permits. Historical normal-only
    rates stay labelled historical, never silently converted or compared as identical.
    Compare ea3d6ad/c77e01c on nano SynDD-val only; lock the better D12 objective
    before reporting tests; tie keeps current c77e01c. Git implementations are loaded
    for measurement only, not retained as alternate runtime paths. overnight_measure.py
    is the authoritative overnight scorer; rescore_drinking.py is historical only.
    Freeze five of the35 original 3MDAD TRAIN drivers via numeric driver sort and
    random.Random(28).sample(...,5); persist exact names in split_freeze.json. Remove
    them from ALL subsequent training, including control/distillation/hard negatives.
    Existing models trained on those drivers are ineligible for clean MDAD-val keep
    decisions. Train clean baselines before the optimization loop; original15 test
    drivers remain untouched. No DAD-only keep decision. No Pi/SSH contact tonight.
    No human food-label results consumed. Data never deleted; one commit per iteration.
