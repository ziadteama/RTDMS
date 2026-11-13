# WESAD → Garmin fatigue training

Public dataset used to train the experimental logistic artifact for the **Garmin RR / `RrHrv`
path**. Labels are lab **baseline vs stress**, not car drowsiness. Amusement and other conditions
are dropped.

## Download

**Preferred (small, HF mirror of E4 wrist + quest):**

```powershell
cd models/physiology
py -3.13 tools/download_wesad_hf.py
# → data/hf_wesad/WESAD/S*/S*_E4_Data/BVP.csv + S*_quest.csv
```

**Official full release** (Uni Siegen / Schmidt et al., ~2.1 GB zip with synchronized
`.pkl` labels): [sciebo](https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx). Unpack to:

```text
models/physiology/data/WESAD/S2/S2.pkl
...
```

(`data/` is gitignored.) `prepare_wesad.py` prefers `.pkl` when present; otherwise uses
E4 `BVP.csv` + `S*_quest.csv` protocol START/END minutes.

## Build windows (Garmin-shaped features)

```powershell
cd models/physiology
pip install -e ".[train]"
python tools/prepare_wesad.py --wesad-root data/hf_wesad/WESAD --out data/wesad_garmin_windows.csv
# or: --wesad-root data/WESAD   # if you have official pickles
```

Pipeline: Empatica `IBI.csv` (preferred) or wrist BVP peaks → RR ms → `RrHrv.add` /
`compute` → keep VALID/DEGRADED rows with `FeatureSnapshot.model_features()` columns.
Condition times come from `S*_quest.csv` when synchronized `.pkl` labels are absent.

Without WESAD files, a smoke CSV can be built for pipeline bring-up:

```powershell
python tools/prepare_wesad.py --synthetic --out data/wesad_garmin_windows.csv
```

## Train

```powershell
python tools/train_model.py data/wesad_garmin_windows.csv models/fatigue_wesad_v1.json `
  --version wesad-baseline-vs-stress-v1-experimental
```

## Live Garmin

```powershell
python -m dms_physiology.garmin_receiver --model models/fatigue_wesad_v1.json
```

`fatigue_probability` is set only when HRV state is `valid` or `degraded`; otherwise it stays null.
