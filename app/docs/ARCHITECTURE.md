# Sahi architecture

Expo SDK 58 (React Native 0.88, New Architecture, Hermes, React Compiler), TypeScript strict,
expo-router, Android development build. Narrative, decisions and divergences:
`Subsystems/Mobile App.md` in the vault. Endpoint shapes: [API.md](API.md).

## Folders

```
app/
├─ src/
│  ├─ app/                 routes only (expo-router)
│  │  ├─ (onboarding)/     consent, permissions, connect (QR), emergency-contacts
│  │  ├─ (tabs)/           drive, trips, settings — each a native Stack
│  │  ├─ diagnostics       hidden screen (tap version 7x, for the Sahi team: hardware health, thresholds, switches, raw metrics)
│  │  ├─ trip/[id]         trip summary + event timeline
│  │  ├─ incident/[id]     clip + sensor timeline (local id, or "pi:<id>" for a Pi-only clip)
│  │  ├─ sos               full-screen countdown (fullScreenModal, no back gesture)
│  │  └─ calibrate, contacts, pair, privacy
│  ├─ screens/             screen bodies the routes render
│  ├─ components/          design-system primitives (Text, Button, Section/Row, Banner, …)
│  ├─ theme/               tokens: colors (neutral + AlertPattern scale), type, spacing, motion
│  ├─ i18n/                en.ts (English strings and keys), t / useT helpers
│  ├─ pi/                  wire types, parsers, transport (HTTP / demo), alert presentation
│  ├─ crash/               crash detector (pure TS) + test fixtures
│  ├─ trips/               trip model, safety score
│  ├─ services/            runtime: poller, trips, alerts, monitor, emergency, permissions
│  ├─ state/               zustand stores, SQLite / secure storage
│  └─ demo/                scripted drive (shared with mock-pi), demo history
├─ modules/sahi-native/    local Expo module (Kotlin): SMS, call, notifications, motion, Wi-Fi
├─ mock-pi/                Node mock of the Pi (no dependencies, runs the TS directly)
└─ scripts/                icon renderer, screenshot script
```

## State

| Store | File | Holds | Persisted |
|---|---|---|---|
| `useSettings` | `state/settings.ts` | consent, onboarding, theme, units, base URL, demo, paused, voice/vibration, crash on/off, call target, emergency number, SOS countdown | SQLite key-value (`expo-sqlite/kv-store`), read synchronously at start |
| `useSecure` | `state/secure.ts` | emergency contacts, Pi hotspot SSID + password | `expo-secure-store` (Android Keystore) |
| `useLive` | `state/live.ts` | connection, last `/status`, `/alert`, `/physio`, GPS speed + fix, armed, armReason | memory only |
| `useDbVersion` | `state/db-api.ts` | a counter bumped on every DB write | — |
| SQLite `sahi.db` | `state/db.ts` | trips, events, HR samples, incidents | yes; `db.web.ts` keeps the same API in memory for the web build |

## Data flow

```mermaid
flowchart LR
  subgraph PI[Pi :8080]
    S["/status"] --- A["/alert"] --- P["/physio"]
  end
  POLL[poller 5 Hz] -->|parse, null on bad input| LIVE[(useLive)]
  S --> POLL
  A --> POLL
  P -->|1 Hz| POLL
  GPS[expo-location<br/>foreground service] --> MON[monitor]
  IMU[sahi-native<br/>accel + gyro 100 Hz] --> MON
  MON -->|speed, location, armed, armReason| LIVE
  MON -->|CrashMonitor| CRASH{crash?}
  CRASH -->|yes| SOS[emergency: incident,<br/>retry queue POST /incident, countdown]
  LIVE --> UI[screens<br/>narrow selectors]
  LIVE --> ALERT[alert engine<br/>notify · voice · haptics]
  LIVE --> TRIPS[trip recorder] --> DB[(SQLite)]
  SOS -->|45 s (configurable), no "I'm OK"| SMS[SMS to contacts<br/>then call emergency number]
```

## The polling loop (`services/poller.ts`)

- Every 200 ms: `GET /status` and `GET /alert` in parallel; every fifth tick also `GET /physio`.
  Each request times out after 1.5 s. The next tick is scheduled after the previous one finishes
  (no overlapping requests on a slow link).
- 3 failed `/status` in a row → `offline` (banner, alert output stops, trip pauses); retries every
  second; if the phone was paired by QR, re-joins the hotspot every 10 s (auto reconnect).
- A 404 on `/alert` or `/physio` marks the endpoint unsupported for 30 s (older `stream.py`).
- Re-renders: screens subscribe with selectors that return primitives or `useShallow` objects, so a
  poll that does not change a value does not re-render its component; the camera view (in setup /
  calibration) never re-renders on a poll, and live video is never rendered while driving. See
  [VALIDATION.md](VALIDATION.md) → performance.

## Alerts (`services/alerts.ts`, `pi/alert.ts`)

Input: `/alert` `pattern` only. On a rise in severity: haptics (per the vibration setting), a voice
line in English (`expo-speech`, `en-US`), and a notification if the app is not
on screen. `repeated` / `continuous` / `max` repeat the voice every 8 / 5 / 4 s while active.
The state-indicator label comes from the models' categorical states in `/status`
(`drowsiness.state`, `hybrid.call` / `texting`); its color from the pattern. No model score is
compared with a threshold anywhere in the app (`grep` for the scores: they are only displayed).

## Crash detector (`crash/detector.ts`)

`detectCrash(samples, gpsSpeeds, config, extras) → CrashEvent | null`, a pure function:

1. armed: phone-only readiness evaluated via pure `armState(inputs)` (`crash/arm-state.ts`):
   enabled, monitoring not paused, fresh GPS fix (≤ 10 s), fresh IMU motion (≤ 1 s), and GPS
   speed > 20 km/h in the 10 s before impact. Independent of Pi connectivity (`live.connection`).
2. impact: |a| > 4 g (gravity included), strongest local peak first;
3. confirm: GPS speed ≤ 5 km/h within 5 s, still ≤ 5 km/h 3 s later (it waits for that GPS data).
   Additionally requires IMU post-impact stillness (`crash/stillness.ts`): low motion (accel
   within 1 g ± 0.25 g and gyro ≤ 0.15 rad/s) for ≥ 3 s within the 6 s following impact.
4. optional checks reported, never required: phone flipped (> 60° gravity rotation), Pi face lost
   (−1…+3 s), head jerk (not in `stream.py` yet → `null`), HR rise ≥ 25 bpm within 30 s.

`CrashMonitor` keeps ~20 s of samples and runs it every 500 ms; one event per impact (60 s
refractory). Tests: `crash/detector.test.ts` (unit, synthetic replay, real-recording replay).

## Incident retry queue (`services/incident-queue.ts`)

Pure-core queue with injected sender and clock:
- State machine: `pending` → `sent` | `failed`.
- Exponential backoff on send failure: 2 s, 4 s, 8 s, 16 s, 32 s, capped at 60 s.
- Idempotent deduplication by `client_id` UUID v4.
- Persisted via KV storage (`sahi.incident-queue`), surviving app restarts.
- `emergency.ts` queues `POST /incident` after SOS decision; delivery failure never blocks SMS or call.

## Emergency SOS & dispatch (`services/emergency.ts`, `services/sos-channels.ts`, `app/sos.tsx`)

- Configurable countdown: `sosCountdownSeconds` setting (30 | 45 | 60 s, default 45 s per Flow 5; manual SOS uses 10 s).
- Configurable number: `emergencyNumber` setting (default '123', presets '123' | '112' | custom 3–15 digits).
- Two-stage flow: on expiry/send, dispatches parallel channels without blocking:
  - **WhatsApp relay**: `POST /v1/sos` (idempotent `client_id` UUID) via the dedicated relay service, authenticated by Bearer API key and `X-Install-Id` UUID v4 (persisted in Keystore). Polled via `GET /v1/sos/{client_id}` every 5 s up to 3 min for delivery receipts (`queued`, `sent`, `delivered`, `read`, `failed`, `opted_out`).
  - **Link-free SMS**: ASCII-only GSM-7 text with 5-decimal coordinates (`Location (paste in Maps): {lat},{lon}`) without URLs, avoiding carrier filtering. Uses Android delivery reports (`sentIntent` + `deliveryIntent` in `sahi-native`), with a single automatic retry after ~60 s if no delivery report is received.
- Real-time status model: per contact and per channel (`queued` | `sent` | `delivered` | `read` | `failed` | `opted_out` | `unknown`). "Delivered" is never shown unless explicitly confirmed by a delivery report.
- Stage 2 emergency call: 15 s window before dialing; accurately reports "Starting call to X", "Calling X" (after dial returns), or "Could not start the call" if dialing fails.

## Foreground service and background sensing

- `expo-location` `startLocationUpdatesAsync` with `foregroundService` (type `location`): its
  ongoing notification ("Sahi is monitoring this trip") keeps the process alive with the screen
  off; fixes arrive in a `TaskManager` task defined at import time.
- Accelerometer + gyroscope come from `sahi-native`, not `expo-sensors`: `expo-sensors` stops its
  listeners on `onHostPause` (see `SensorProxy.kt`), which would blind the detector in the
  background. The module samples at 100 Hz on its own thread and sends one batch per 200 ms.

## Native module `sahi-native` (`modules/sahi-native`, Android only)

| Function | Android API | Why native |
|---|---|---|
| `sendSms(numbers, text)` | `SmsManager.sendMultipartTextMessage` | send without a tap (needs `SEND_SMS`) |
| `call(number)` | `Intent.ACTION_CALL` | call without a tap (needs `CALL_PHONE`) |
| `notify(id, channel, title, body, url)` / `cancel(id)` | `NotificationCompat`, channels `alerts` and `sos` (alarm sound, full-screen intent) | avoids `expo-notifications`, which bundles Firebase Messaging |
| `startMotion(hz)` / `stopMotion()` + `onMotion` event | `SensorManager` on a `HandlerThread` | keeps sampling in the background |
| `joinWifi(ssid, password)` / `unbindNetwork()` | `WifiNetworkSpecifier` + `bindProcessToNetwork` | the hotspot has no internet |
| `hasTelephony()` | `PackageManager.FEATURE_TELEPHONY` | tablets |

Its manifest adds the permissions and `usesCleartextTraffic` (the Pi serves plain HTTP). On iOS /
web the module is `null` and callers fall back (open the SMS composer / dialer, which need a tap).

## Failure policy

| Situation | What the app does |
|---|---|
| Unit not connected | banner ("Unit not connected. Check it is powered on.") + reconnect loop; state shows "Unit not connected" in neutral grey; no phone alerts (the unit's buzzer does not depend on the phone); trip ends after 60 s offline; crash detection remains armed on phone (phone-only IMU + GPS, independent of unit link) |
| Unit without a proposed endpoint | that feature hides or shows a banner; nothing is guessed |
| Bad JSON / missing fields | parser returns `null` (or a `null` field); UI shows "—", never 0 |
| GPS lost (no fix 10 s) | banner "No GPS: crash detection is off"; the detector cannot arm or confirm; manual SOS still works |
| Location permission denied | as GPS lost; SOS SMS says "location unknown" |
| SMS / phone permission denied | SOS opens the SMS composer and the dialer (needs a tap) |
| Notifications denied | voice + haptics still work while the app is open |
| No emergency contacts | SOS skips SMS and calls the configured emergency number (default 123) |
| Crash while the app is in the background | `sos` notification with a full-screen intent opens the countdown |
| App killed mid-trip | the open trip is closed at its last recorded moment on next start |
| Monitoring paused | poller, trips, alerts and crash detection all stop; the unit keeps buzzing |
