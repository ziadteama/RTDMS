# Pi runtime skeleton

`rtdms-pi` connects immutable model reports to `dms_fusion` and plays its decisions.
A watchdog drops stale camera reports after 2 seconds and watch reports after 10 seconds.
There are no runtime risk thresholds. Garmin packets stay in memory; physiology runs
in-process, so there is no separate `rtdms-physiology.service`. P3 will own the single
GATT server and call `GarminPhysioSource.handle_write`.

From the repository root:

```sh
docker compose -f pi/compose.yaml run --rm verify
docker compose -f pi/compose.yaml run --rm verify-py313
```

Without Docker, install `fusion`, `models/physiology`, and `pi[dev]` editable in a
virtualenv, then run `pytest && ruff check . && mypy src` from `pi/`.
The Docker build uses the repo root (`docker build -f pi/Dockerfile .`).

Defaults use no hardware: `rtdms-pi --no-camera --buzzer none --port 8080`.
Debug endpoints: GET `/alert`, `/status`, `/physio`, `/health`; POST `/test_alert`
with `{"pattern":"short_beep"}`. Test alerts last 2 seconds, then resume live output.
HTTP defaults to `::`; use `--host 127.0.0.1` for local-only debugging. Authentication
and BLE belong to P3; this debug server is intended for a trusted development network.
Health `cpu_pct` measures process CPU time over server uptime.

Use `--camera` to load the existing distraction pipeline, `--buzzer gpio`, optional
`--vibration-pin`, and `--physiology` for the in-memory Garmin adapter. See `--help`
for pins, rotation, freshness, tick rate and HTTP configuration. `RTDMS_BUZZER_PIN`,
`RTDMS_VIBRATION_PIN`, `RTDMS_STALE_S`, `RTDMS_PHYSIO_STALE_S`, `RTDMS_TICK_RATE`,
`RTDMS_HTTP_PORT`, `RTDMS_HOST`, and `STATE_DIRECTORY` supply environment defaults.
The state directory is reserved; this skeleton does not persist reports.

Current stream hybrid output provides action confidence but no `phone_score` or
`sustained_phone_ms`. Those fusion inputs remain None unless supplied upstream;
the adapter does not infer duration or reinterpret action confidence as a phone score.
The Garmin adapter has no trained model configured, so fatigue probability stays None.

Not verified on hardware:

- Pi camera / LiteRT / hybrid pipeline, including shutdown of a blocked camera read.
- GPIO TonalBuzzer and optional vibration output.
- Garmin BLE transport (not started here), Pi HRV integration and systemd deployment.

The image verifies fakes and in-memory physiology on x86; it does not install the
vision stack or provision model assets. The service uses the placeholder account
`rtdms`; create it and grant hardware permissions before installation. Its defaults
are hardware-free. The upstream vision script owns its existing event log and
calibration paths; provision writable paths before enabling it under systemd.
