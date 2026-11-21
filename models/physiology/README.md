# DMS Physiology

Lightweight, quality-gated PPG processing for a Raspberry Pi 5 Driver Monitoring System.

Two live paths feed the same fusion contract (`fatigue_probability` + quality/state):

- **Garmin FR265** — watch RR ms → `RrHrv` → optional `models/fatigue_wesad_v1.json`
  (`python -m dms_physiology.garmin_receiver --model models/fatigue_wesad_v1.json`).
  Training / role: `docs/WESAD.md` and vault `[[Physiology Fusion Approach]]`.
- **MAX30102 / ESP** — raw PPG over BLE → peaks → PRV → same JSON logistic loader.

Bad / invalid windows suppress fatigue output (`null`); fusion owns alerts.

## Runtime design

- Python 3.11 on Raspberry Pi OS 64-bit
- 100 Hz PPG input, one optical channel in version 1
- NumPy, SciPy, Bleak, and the standard library only at runtime
- HR every second, PRV and model output every five seconds after a 60-second warm-up
- Bad signal quality suppresses fatigue output

`scikit-learn` is used only for offline model training. Deployment loads a small JSON artifact and calculates the logistic-regression score directly.

## Development

Docker is the canonical development and CI environment. It ensures the required Python 3.11 runtime even when the workstation has a different Python version.

```powershell
docker compose run --rm verify
docker compose run --rm simulate
```

For a local environment, install Python 3.11, then create a virtual environment and install the development and training extras:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,train]"
pytest
ruff check .
mypy src
```

See `docs/ARCHITECTURE.md` and `docs/VALIDATION.md` for the interface and scientific-validation plan.
