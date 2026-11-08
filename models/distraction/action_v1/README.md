# action_v1 / v2: action classifier research

Research code and reports behind the v2 phone model (`../models/action_v2/`, run by
`../scripts/stream.py --hybrid`). Instead of detecting the phone as a box, it classifies what the
driver is doing from a crop around the face, then confirms a phone at the ear or in the lap.

## What to read

| File | What it is |
|---|---|
| `REPORT_v2.md` | **Start here.** The hybrid v2 system: alert rules, results against the det_v2d release model, speed |
| `REPORT.md` | v1: the action classifier alone (7 classes), training and results |
| `DECISIONS.md` | Every design decision (D1, D2, ...) with the reason |
| `FINDINGS.md`, `PROGRESS.md` | Working notes and run log |
| `class_map.json` | How each dataset's labels map to the 7 classes |
| `splits/3mdad.json` | Driver split for 3MDAD (train / val / test by driver) |
| `report_assets/` | Confusion matrices and example frames used in the reports |

## Code (`src/`)

| Step | Scripts |
|---|---|
| Crop extraction from the video datasets | `extract.py`, `run_extract.sh`, `run_extract_v2.sh` |
| Build classifier datasets | `build_cls.py`, `build_cls_v2.py`, `build_phone.py`, `build_lap.py`, `augment.py` |
| Train | `train_cls.py`, `run_s.sh`, `run_after_act.sh` |
| Evaluate (clip level, alert level) | `evaluate.py`, `evaluate_v2.py`, `alerts.py`, `examples.py` |
| Speed | `bench.py`, `bench_v2.py` |
| Release-model comparison | `release_run.py`, `release_ebdd.py` |

`alerts.py` is the same rule code the Pi uses (`../scripts/hybrid_alerts.py` is a copy).

## Not in the repo

- **Data:** SynDD, 3MDAD, DAD and EBDD frames and crops (tens of GB) live outside git, at
  `D:\rtdms-data` on the training PC. The scripts use those paths directly, so they are research
  code: change the paths before running them anywhere else.
- **Training runs and base weights** (`runs/`, `*.pt`). Only the three INT8 NCNN models the Pi needs
  are shipped, in `../models/action_v2/` (checksums in `../models/README.md`).
- Dataset licences are the same as for det_v2d (see `../models/README.md`): research and education
  only.
