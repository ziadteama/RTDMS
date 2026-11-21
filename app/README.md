# Sahi (صاحي)

The RTDMS driver's phone app (Android). It shows what the Pi in the car sees and decides, speaks
and vibrates with the Pi's alerts, keeps a history of trips with a safety score, and after a crash
counts down 30 s and then sends an SMS with the location to emergency contacts and calls 123.
Everything stays on the phone and the Pi: no accounts, no cloud.

Project note (status, decisions, divergences from the spec): `Subsystems/Mobile App.md` in the
vault. Code docs: [ARCHITECTURE](docs/ARCHITECTURE.md) · [API](docs/API.md) ·
[DESIGN](docs/DESIGN.md) · [VALIDATION](docs/VALIDATION.md) · [EVIDENCE](docs/EVIDENCE.md) ·
[screenshots](docs/screenshots/).

Expo SDK 58 · React Native 0.88 · TypeScript strict · expo-router · a local Kotlin module
(`modules/sahi-native`) · **development build** (Expo Go cannot load the native module).

## Install

Node ≥ 22.18, JDK 17, Android SDK (platform 37, build-tools 37, NDK 27.1) or Android Studio.

```bash
cd app
npm install
```

## Run on your Android phone

1. Phone: Settings → About → tap *Build number* 7× → Developer options → **USB debugging** on.
   Plug it in and accept the prompt (`adb devices` lists it).
2. Build and install the development build (first time, and after any native change):

   ```bash
   npx expo run:android --device
   ```

   Or without a local Android SDK: `npx eas-cli@latest build --profile development --platform android`
   and install the APK it links.
3. Day to day, only the JavaScript bundler:

   ```bash
   npx expo start --dev-client
   ```

   The dev build on the phone connects to it (same Wi-Fi as the laptop, or `adb reverse tcp:8081 tcp:8081` over USB).

## Point it at the mock Pi (no hardware)

```bash
npm run mock                         # http://0.0.0.0:8080, a scripted two-minute drive, looping
npm run mock -- --freeze 92          # hold one moment (92 s = drowsy) for screenshots
npm run mock -- --replay drive.jsonl # replay /status recorded from a real Pi (npm run mock:record)
```

In the app: Settings → **Pi address** → `http://<laptop LAN IP>:8080` (phone and laptop on the
same Wi-Fi). Over USB instead: `adb reverse tcp:8080 tcp:8080` and use `http://127.0.0.1:8080`.

**Demo mode** (Settings → Demo mode, or "Try demo mode" while pairing) needs neither the Pi nor
the laptop: the same scripted drive runs inside the app, with sample trip history and a
"Simulate a crash" button that goes through the real crash detector.

## Point it at the real Pi

1. On the Pi, run the pipeline with the API (`models/distraction/scripts/stream.py`, port 8080) and
   its Wi-Fi hotspot (Pi at `10.42.0.1`).
2. In the app: Settings → **Pair with QR code** and scan the QR on the unit
   (`WIFI:T:WPA;S:<ssid>;P:<password>;U:http://10.42.0.1:8080;;`, see [API.md](docs/API.md#pairing-qr-code)).
   The phone joins the hotspot and keeps using mobile data for SMS and calls.
   Or type the address by hand (Settings → Pi address).

Today's `stream.py` serves `/status`, `/stream.mjpg` and `/calibrate`. The other endpoints in
[API.md](docs/API.md) are proposed; until the Pi has them the app hides those parts
(heart group, Pi health details) and shows "this Pi does not report fusion alerts yet".

## Gates

```bash
npx tsc --noEmit                         # types (strict)
npx eslint .                             # lint (expo config + React Compiler rules)
npm test                                 # unit + replay tests (jest-expo)
NODE_USE_ENV_PROXY=1 npx expo-doctor     # dependency / config checks (the env var only behind a proxy)
```

The crash detector's real-recording replay test runs when the dataset is present:
`npm run fetch:driving-data` (clones the public driverBehaviorDataset into `.data/`, git-ignored).

Release checklist and device checks: [VALIDATION.md](docs/VALIDATION.md). What has actually been
measured: [EVIDENCE.md](docs/EVIDENCE.md).

## Layout

```
src/app/        routes (expo-router)          src/services/  poller, trips, alerts, crash monitor, SOS
src/screens/    screen bodies                 src/crash/     crash detector (pure TS) + tests
src/components/ design-system primitives      src/pi/        API types, parsers, transport
src/theme/      tokens                        src/state/     stores, SQLite, secure storage
src/i18n/       en only                       src/demo/      scripted drive (shared with mock-pi)
modules/sahi-native/  Kotlin: SMS, call, notifications, background motion, Wi-Fi join
mock-pi/        Node mock of the Pi           scripts/       icon renderer, screenshots
```

Android only: iOS cannot send an SMS or start a call without a tap, so the emergency flow is
Android-first (on iOS the module is absent and the app opens the composer / dialer instead).
