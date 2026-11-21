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
The state directory stores the pairing token; reports and settings remain in memory.

Current stream hybrid output provides action confidence but no `phone_score` or
`sustained_phone_ms`. Those fusion inputs remain None unless supplied upstream;
the adapter does not infer duration or reinterpret action confidence as a phone score.
The Garmin adapter has no trained model configured, so fatigue probability stays None.

Not verified on hardware:

- Pi camera / LiteRT / hybrid pipeline, including shutdown of a blocked camera read.
- GPIO TonalBuzzer and optional vibration output.
- Garmin BLE transport, Pi HRV integration and systemd deployment.

The image verifies fakes and in-memory physiology on x86; it does not install the
vision stack or provision model assets. The service uses the placeholder account
`rtdms`; create it and grant hardware permissions before installation. Its defaults
are hardware-free. The upstream vision script owns its existing event log and
calibration paths; provision writable paths before enabling it under systemd.


## BLE phone service (P3)

Install the existing physiology package alongside `rtdms-pi[ble]`. BLE defaults on
when bless is importable and camera mode is enabled. `--ble` explicitly enables it;
`--no-ble` disables it. `--fake-ble` starts the simulated transport, including with
`--no-camera`. `--ble-name` / `RTDMS_BLE_NAME` defaults to `RTDMS-Pi`.
`STATE_DIRECTORY` / `--state-dir` supplies the directory for `token`; its existing
pairing token is reused. Never put the token in logs or command-line arguments.

The GATT table has **11 characteristics**: ten phone entries plus Garmin, on one
service. The task's requested test count of 12 conflicts with the contract table;
the implementation and tests follow the table. Phone writes require auth; Garmin
writes bypass phone auth and synchronously reuse `GarminPhysioSource.handle_write`
and `GarminRrReceiver.handle_write`. Reads remain available without auth.
Invalid JSON/schema writes are counted and dropped; unknown properties are stripped.
Unknown command names fail the enum schema and are dropped; dispatch failures return
bounded errors. Restart/shutdown callbacks only log by default.

`ble/contract.py` caches all validators once. It searches `RTDMS_CONTRACT_DIR`, then
repository ancestors (`contracts/pi-link`, the single source of truth; no vendored copy,
the Pi deploys the monorepo checkout). `jsonschema`, already a dev dependency, is also a runtime dependency.
Settings and incident metadata are in-memory only. Settings do not yet change fusion
thresholds. Incident IDs derive from the phone's `t_crash` in UTC; clock offset is
saved separately for Pi ring-buffer alignment. The golden incident fixture's ID
uses 2026 while its timestamp is in 2024; generated IDs follow the timestamp.

Pattern transitions are queued without transport I/O on the runtime thread, then
sent by the BLE scheduler (10 ms polling); keep-alive is 5 Hz, status 2 Hz, physio
1 Hz. Loss above 5% of the latest 60 packet outcomes halves status/physio rates;
below 2% restores them. Sequence gaps and rejected packets feed the monitor.

### Known limits

**Not verified on hardware.** bless 0.2.x exposes no usable central disconnect
callback, and BlueZ D-Bus properties (`org.bluez.Device1.Connected`) are not
monitored or exposed by the library. To prevent authentication from persisting
indefinitely across disconnects and new client connections, `AuthGate` enforces
an authentication time-to-live (`ttl_s`, default 300 s) since the last accepted
authentication or authenticated write. When the TTL expires, writes to protected
characteristics are rejected with `GattWriteRejected("insufficient authentication")`
until `Char.AUTH` is re-written. The mobile application re-authenticates on every
connect. An explicit `on_disconnect()` hook remains available for deployments that
supply an external connection-tracking signal.

ATT insufficient-authentication mapping is best-effort (log and re-raise); actual
BlueZ behavior needs hardware verification. Disconnect never stops advertising.
MTU negotiation, simultaneous watch/phone access, radio loss and reconnect behavior
remain hardware integration gates.

Laptop stand-in (not run by gates):

```sh
python pi/tools/phone_sim_client.py --name RTDMS-Pi --samples 10
```

The client prompts for a token without echo (or accepts `--token-file`), authenticates,
sends clock sync, subscribes to telemetry/results, and reports write-to-result p50/p95.
Its default probe sends `test_alert` with pattern `none` (a two-second silent override).
`--test-alert` uses `max`; `--incident` reports a synthetic incident. Use on a test
setup. No shutdown/restart command is sent. P3 captures metadata only, not video clips.


## Settings and Thresholds (P6)

Settings are persisted to `$STATE_DIRECTORY/settings.json` (mode 0600, atomic write via temporary file).
Detector toggles (`detectors.drowsiness`, `detectors.distraction`, `detectors.phone`, `detectors.physiology`)
are gated via pure function `apply_settings()` in `rtdms_pi.detector_gate`. Disabling a detector blanks (sets to `None`)
its input before calling `dms_fusion.decide()`, and is reflected as `"unavailable"` in `/status` and `"off"` in the
`health` payload's `models` capability map.

### Settings not yet applied

Threshold parameters defined in the mobile-Pi contract (`settings.schema.json`) are stored, persisted, and exposed
via BLE/HTTP, but cannot yet be applied by the Pi runtime because underlying detection models and the fusion engine
use hard-coded threshold constants. To prevent divergent logic, `pi/` does not invent thresholds locally.

| Setting | Type / Range | Default | Owning Subsystem | Reason not yet applied |
|---|---|---|---|---|
| `eye_closure_s` | float (0.5 – 10.0 s) | `2.0` | Vision / drowsiness model | Fixed internal temporal closure window in upstream eye state analyzer; not exposed for dynamic parameterization. |
| `offroad_gaze_s` | float (0.5 – 10.0 s) | `2.0` | Vision / distraction model | Fixed threshold in upstream gaze vector classifier. |
| `phone_s` | float (0.2 – 10.0 s) | `1.0` | Fusion (`dms_fusion`) | Fixed internal threshold evaluating `sustained_phone_ms` in `dms_fusion.decide()`. |
| `sensitivity` | enum (`low`, `normal`, `high`) | `normal` | Fusion (`dms_fusion`) | Requires fusion-level sensitivity scaling over multimodal fusion matrices and alert escalation curves. |

### Proposal to Fusion Owner (Need)

**Feature Request: Parameterized Thresholds in `dms_fusion.decide()`**

To allow user-configured driver profiles and runtime sensitivity adjustments from the Sahi mobile app to take effect in real time, `dms_fusion.decide()` should accept threshold arguments:

```python
def decide(
    face: Mapping[str, object] | None,
    phone: Mapping[str, object] | None,
    physiology: Mapping[str, object] | None,
    *,
    phone_s: float = 1.0,
    sensitivity: str = "normal",  # "low" | "normal" | "high"
) -> FusionDecision:
    ...
```

- **`phone_s`**: Replaces the hard-coded phone duration threshold for triggering distraction alerts.
- **`sensitivity`**: Scales confidence cutoffs and escalation latencies (e.g., faster alert escalation for `"high"`, higher tolerance for `"low"`).

The Pi runtime already validates, stores, and serves these values in `rtdms_pi.settings.SettingsStore`. Once `dms_fusion` exposes these parameters, `rtdms_pi.runtime.Runtime` can forward them directly on each evaluation frame.
