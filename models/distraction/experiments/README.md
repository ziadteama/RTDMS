# Experiments

The scripts behind every result in [../docs/OVERNIGHT_REPORT.md](../docs/OVERNIGHT_REPORT.md). They
are research code: not linted or unit-tested like `src/` and `scripts/`, but each one runs from this
folder on any machine. `_paths.py` finds the package root by itself and reads the data root from
`configs/data.yaml` (override with `RTDMS_DATA=/path/to/data`). Run them from `models/distraction/`:

```bash
python experiments/<script>.py <arguments>
```

Most need the datasets from [../docs/REPRODUCE.md](../docs/REPRODUCE.md) and, for the SynDD sweeps, the
face / detection caches that `scripts/eval_simple.py` writes (run it once per weights file first).

## Tests on data never used in training (report section 9)

| Script | What it does | Example |
|---|---|---|
| `mdad3_eval.py` | 3MDAD front camera, 50 drivers × 13 actions: every clip through the live simple-mode pipeline; per-action share of clips with the right alert | `python experiments/mdad3_eval.py run 6`, then `summary` |
| `dad_eval.py` | DAD real IR (front + top camera, 3 drivers): action clips + 66 min of normal driving → alerts and false alarms per hour | `python experiments/dad_eval.py run 6` |
| `int8_check.py` | frame-level precision / recall and speed of NCNN models (FP32 vs INT8) on SynDD validation frames | `python experiments/int8_check.py models/det_v2d_ir_512_ncnn_model models/det_v2d_ir_512_det_aciq_mixed_ncnn_model` |
| `frame_val.py` | Ultralytics `val` (P / R / AP50) of a `.pt` model on one or more YOLO data yamls | `python experiments/frame_val.py models/det_v2d_ir_512.pt 512 <data.yaml>` |

`mdad3_eval.py` and `dad_eval.py` use `RTDMS_MODEL=det_v2d` (default) or `det_v2h` to pick the model.

## The "8 additions" (report section 8)

| # | Script | What it does |
|---|---|---|
| 1 | `sam_recover.py` | SAM 2 tracks the phone forward / backward from each teacher box to fill frames the teacher missed |
| 2 | (`scripts/fetch_syndd.py --views`, `scripts/label_video_boxes.py --view`) | dashboard + side-window SynDD views for training |
| 3 | `fisheye_roi.py` | SynDD frame → simulated 160° fisheye sensor → live `DriverROI` rectification (training + test views) |
| 1–3 | `extend_set.py` | merged_b + extra training frames (hard links) as a new YOLO set |
| 6 | `cv5.py` | 5-fold cross-validation by driver: `build`, `train <k>`, `resume <k>`, `eval <k>`, `all`, `summary` |
| A / B | `rich_pass.py`, `rules_ab.py` | cache head pose / gaze / jaw / pose keypoints per frame; replay and tune the texting (A) and eating (B) rules |
| speed | `bench_simple.py` | simple-mode FPS with the texting rule on / off on a video |

## Ideas A–G and threshold tuning (report sections 3 and 7)

| Script | What it does |
|---|---|
| `sweep.py`, `sweep_model.py` | phone / drink threshold sweeps on cached detections (validation) |
| `test_final.py` | score the chosen setting once on the test drivers |
| `sweep_track.py` | idea A: ByteTrack-style keep-alive of weak boxes |
| `temporal_model.py` | idea B: small 1D-conv temporal model on per-frame features |
| `crop_pass.py`, `sweep_crop.py` | idea C: second detector pass on a zoomed head-and-shoulders crop |
| `label_a2.py` | idea D: pseudo-labels for the unlabelled SynDD A2 drivers |
| `copy_paste.py` | idea E: paste real IR phone cut-outs next to ears |
| `hard_cases.py` | idea G: results split by appearance (hat, sunglasses) |
| `phone_baseline.py` | per-frame phone detection rate of several models on held-out drivers |
| `box_sheet.py`, `rf_sheet.py` | contact sheets to check labels by eye |

None of the ideas A–G, nor additions 1–3, beat the release model; the report explains why. Their
outputs (JSON results, contact sheets) were written under `<data root>/runs/overnight/`.
