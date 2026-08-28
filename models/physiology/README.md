# DMS Physiology

Lightweight, quality-gated PPG processing for a Raspberry Pi 5 Driver Monitoring System.

The wearable sends raw MAX30102 samples through BLE. This service derives heart rate, pulse-rate variability (PRV), signal quality, and an optional fatigue probability for multimodal DMS fusion.

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
