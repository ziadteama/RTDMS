# DMS fusion stub

Consumes model OutputSink JSON and maps risk → alert pattern. **Owns** cabin alert
decisions. Models only report scores + quality.

Pi-first: keep this process tiny; no ML here.

## v0 behaviour

- Reads the latest in-memory / file replay dicts from physiology, face, and phone.
- Escalates: phone sustained → continuous; face drowsy → repeated.
- Physiology is accepted but does **not** change alerts (no physio-only beep, no "physio
  confirms" → max): on MPD-DF heart rate added nothing beyond drive time. See
  `Subsystems/Physiology Decision Log.md`.
- GPIO optional later.

```bash
cd fusion
pip install -e ".[dev]"
pytest
python -m dms_fusion.stub_demo
```
