# Held-object drinking results

Date: 2026-11-14; dataset held_object_v2; manifest SHA256 `93f349326c7835c2fdab2dde30ce80feb1ed61e1c8d89dee52e84d5e4c816565`.

FP32/available backend, no INT8 claim. New thresholds selected only on SynDD-val.

| Dataset | OLD labels drinking / FA/h | Release detector drinking / full-hybrid FA/h | Live Pi | NEW drinking / FA/h |
|---|---|---|---|---|
| syndd | [10, 18] / 9.67741935483871 | [15, 18] / 0.0 | OFF, 0 alerts | [10, 18] / 4.838709677419355 |
| 3mdad | [0, 30] / 0.0 | [22, 30] / 14.2 | OFF, 0 alerts | [0, 30] / 0.0 |
| dad | [2, 2] / 0.9003614951402992 | [2, 2] / 79.2 | OFF, 0 alerts | [1, 2] / 0.9003614951402992 |

FA/h is normal+hand_on_face for this standalone drinking rule; release FA covers the full hybrid.

## S3.1–S3.2 Crop classification (gated frames with original known binary labels)

| Set/model | Class | Precision | Recall | F1 | Support | Confusion (cup,empty) |
|---|---|---|---|---|---|---|
| syndd/v2_s/fp32 | cup_bottle | 0.9487 | 0.8436 | 0.8931 | 307 | [[259, 48], [14, 3857]] |
| syndd/v2_s/fp32 | empty_hand | 0.9877 | 0.9964 | 0.9920 | 3871 | [[259, 48], [14, 3857]] |
| 3mdad/v2_s/fp32 | cup_bottle | 0.7350 | 0.8522 | 0.7893 | 1949 | [[1661, 288], [599, 4108]] |
| 3mdad/v2_s/fp32 | empty_hand | 0.9345 | 0.8727 | 0.9026 | 4707 | [[1661, 288], [599, 4108]] |
| all_heldout | cup_bottle | 0.7580 | 0.8511 | 0.8018 | 2256 | [[1920, 336], [613, 7965]] |
| all_heldout | empty_hand | 0.9595 | 0.9285 | 0.9438 | 8578 | [[1920, 336], [613, 7965]] |

## S3.3 Event counts

| Dataset | True drinking clips | Missed clips | False alerts | Normal hours | FA/h |
|---|---|---|---|---|---|
| syndd | 10/18 | 8 | 1 | 0.20666666666666667 | 4.838709677419355 |
| 3mdad | 0/30 | 30 | 0 | 0.5617591666666667 | 0.0 |
| dad | 1/2 | 1 | 1 | 1.1106649999999996 | 0.9003614951402992 |

## S3.4 False-alert breakdown

| Dataset | Original label | False drinking onsets |
|---|---|---|
| syndd | eating | 0 |
| syndd | neg_control_panel | 0 |
| syndd | neg_hand_on_head | 0 |
| syndd | neg_reaching | 0 |
| syndd | neg_singing | 0 |
| syndd | neg_talking | 0 |
| syndd | neg_yawning | 1 |
| syndd | normal | 0 |
| syndd | phone_in_hand | 0 |
| syndd | phone_left_ear | 1 |
| syndd | phone_right_ear | 0 |
| 3mdad | AC1 | 0 |
| 3mdad | AC10 | 0 |
| 3mdad | AC11 | 0 |
| 3mdad | AC12 | 0 |
| 3mdad | AC15 | 0 |
| 3mdad | AC16 | 0 |
| 3mdad | AC2 | 0 |
| 3mdad | AC3 | 0 |
| 3mdad | AC4 | 0 |
| 3mdad | AC5 | 0 |
| 3mdad | AC6 | 0 |
| 3mdad | AC7 | 0 |
| 3mdad | AC8 | 0 |
| dad | adjusting_radio | 0 |
| dad | messaging_left | 0 |
| dad | messaging_right | 0 |
| dad | normal_driving_1 | 0 |
| dad | normal_driving_2 | 0 |
| dad | normal_driving_3 | 1 |
| dad | normal_driving_4 | 0 |
| dad | normal_driving_5 | 0 |
| dad | normal_driving_6 | 0 |
| dad | reaching_behind | 0 |
| dad | talking_with_passenger | 0 |
| dad | talking_with_phone_left | 8 |
| dad | talking_with_phone_right | 3 |

## S3.5 / S4.2 Could not do or verify

PC four-thread latency (FP32/available backend): `{"backend": "v2_s/fp32", "threads": 4, "pose_ms": 11.897292995126918, "crop_ms": 3.2046830013860017, "gate_rate": 0.1790943930445725, "extra_pc_ms": 4.5397050887424575, "extra_pi_estimate_ms": 9.53338068635916, "worst_gate_pi_estimate_ms": 15.057939399499448, "pi_estimate_only": true, "pi_reachable": false, "pi_status": "open", "ssh_output": "ssh: connect to host 192.168.100.181 port 22: Connection timed out\n", "target_ms": 10}`.
Pi concurrent FPS/latency and wrist check BLOCKED: need reachable key-auth Pi with running phone+face pipeline and ~20 camera frames. Labelled Pi IR evaluation additionally needs a labelled Pi set. x2.1 values are estimates only.
INT8 BLOCKED by Application Control on ncnn2table; need an authorized environment/toolchain. No policy or executable changes attempted.
No explicit rubbing-eyes action label found in the supplied action maps; need independently identified labelled clips. No silent substitution.
Forehead mapping: SynDD neg_hand_on_head; 3MDAD AC2 hair/makeup is an imperfect proxy, reported as AC2. AC12 fatigue is not silently called rubbing eyes.
CLIP k selection is numerical and provisional until candidate contact sheets are inspected. Pseudo-food labels never entered binary training. Uncertain stays unresolved.
Classification excludes unmapped original action labels rather than guessing ground truth; all actions remain in event evaluation and eval_test manifest.
Three-class gate and before/after counts are in versioned JSON/CSVs. Models and generated images remain ignored. Final documentation/visual review remains pending.


## D34 correction pending detached re-selection

Old rule (frame-rate bug): 3MDAD 0/30. A .3s window pruned all prior samples at
3fps; correction follows frame-spacing reasoning, not test-score optimization.
Both historical results and forthcoming fixed-rule results are retained.
Live Pi drinking baseline is OFF (`--no-detect`), 0 drinking alerts.
Historical Phase B loose SynDD-test10/18,9.7 FA/h is worse than release15/18,0 FA/h.
Fixed-rule SynDD-val selection and subsequent test scoring run as JOB rulefix.
