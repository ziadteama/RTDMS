# What must pass before a Sahi release

What *has* passed, with dates and environments: [EVIDENCE.md](EVIDENCE.md).

## 1. Gates (every change)

| Gate | Command | Pass |
|---|---|---|
| Types | `npx tsc --noEmit` | no output, exit 0 |
| Lint | `npx eslint .` | 0 problems (includes the React Compiler rules: pure render, no state set in effects) |
| Tests | `npm test` | all suites pass; the real-recording replay suite **ran** (not skipped) when `.data/` exists |
| Expo doctor | `npx expo-doctor` (`NODE_USE_ENV_PROXY=1` behind a proxy) | all checks pass |
| Android build | `npx expo prebuild -p android && cd android && ./gradlew assembleDebug` | `BUILD SUCCESSFUL`, APK produced |
| No hardcoded styles in screens | `grep -rnE "#[0-9a-fA-F]{3,8}\b\|fontSize\|fontWeight" src --include=*.tsx \| grep -v src/theme/` | only the comment in `text.tsx` |
| No thresholds on model scores | `grep -rnE "perclos\|openness\|blink_rate\|fatigue_probability\|\.p\b" src --include=*.ts* \| grep -v test \| grep -E "[<>]=?"` | hits only in `pi/parse.ts` (a probability outside 0–1 is rejected as bad input) and `demo/scenario.ts` (generates mock data); none decides an alert |
| No network beyond the Pi | `grep -rnE "fetch\(\|https://" src --include=*.ts*` | only `pi/transport.ts` (the Pi), the Maps link text inside the SOS SMS, and the incident screen's "Open in Maps" (the driver's tap hands it to the Maps app) |

Read the output, not the exit code (Agent Guide §4).

## 2. Unit and replay tests (`npm test`)

| Suite | Covers |
|---|---|
| `src/crash/arm-state.test.ts` | pure `armState` logic: armed on enabled + fresh GPS/motion + speed > 20 km/h; disarm reasons (`disabled`, `no_gps`, `no_motion`, `too_slow`); precedence and staleness boundaries |
| `src/services/incident-queue.test.ts` | pure incident queue: retries with exponential backoff (2 s to 60 s cap), deduplication by `client_id`, persistence round-trip surviving restart, success removes entry and records receipt |
| `src/crash/detector.test.ts` | spike + stop → event; spike, no speed drop → none; below 20 km/h → none; < 4 g → none; stop too late → none; stop that does not hold → none; waits for GPS; null speed never arms; optional checks; streaming wrapper fires once; native batch unpacking |
| same, *replay: hardening cases* | dropped phone while stationary (no prior speed) → none; dropped phone while driving then picked up and moved → none (no stillness); speed bump at 30 km/h (3.5–4.5 g spike then continued motion) → none; roller-coaster repeated spikes with sustained motion → none; real-crash positive still passes; missing GPS with IMU stillness → none (requires speed gating & confirmation) |
| same, *replay: normal driving* | 20 min synthetic city drive (bumps to 2.5 g, hard braking, stops at lights) → no event; same drive + injected 5, 6, 7, 8 g impact → detected at the impact |
| same, *replay: real recorded driving* | driverBehaviorDataset trips 16, 17, 20, 21 (~51 min, mounted phone, aggressive braking / turns) under the worst case (always armed, stop after every candidate) → no event; trip 16 + injected 5–8 g → detected |
| `src/pi/parse.test.ts` | `/status` exactly as `stream.py` serves it (initial, v1 levels, v2 drowsiness + hybrid) round-trips; garbage → null; bad fields dropped, never invented; every second of the mock scenario round-trips; `/alert`, `/physio`, `/health` (throttle bits), `/settings`, `/incidents`; pairing QR and typed address |
| `src/pi/alert.test.ts` | every `AlertPattern` mapped, in fusion order; output never gets quieter as severity rises; escalation; driver-state labels per scenario phase and for v1 levels; voice line per state |
| `src/trips/score.test.ts` | safety score examples, monotonicity, short-trip floor; weekly trend |
| `src/utils/format.test.ts` | duration labels |
| `src/services/phone.test.ts` | E.164 phone normalization, Egypt local prefixes (010, 011, 012, 015) to +20, validation |
| `src/services/sos-message.test.ts` | GSM-7 charset assertion, length <= 160 for worst-case coordinates/time, 5 decimals, no URL, crash and manual variants with/without location |
| `src/services/relay/client.test.ts` | relay client against fake fetch: Bearer and X-Install-Id headers, 8 s timeout on /v1/sos (10 s default), 429 rate limit handling, bad JSON / schema invalid -> null |
| `src/services/sos-channels.test.ts` | parallel WhatsApp relay + link-free SMS dispatch; relay failure never blocks SMS; SMS delivery reports, retry after 60 s without delivery report; never-delivered-unless-reported status invariant; 5 s polling of /v1/sos/{id} |
| `src/state/secure-install-id.test.ts` | random UUID v4 install ID created on first run, persisted in Keystore, wiped on reset |

## 3. Device checks (a phone, a dev build or release build)

Run on a **mid-range Android** (e.g. Snapdragon 6-series / Helio G85 class, 4–6 GB RAM),
release build (`npx expo run:android --variant release`), not Expo Go, not the debugger.

| # | Check | How | Pass |
|---|---|---|---|
| D1 | Frame rate on Live while polling | Developer options → *Profile HWUI rendering* (bars) or `adb shell dumpsys gfxinfo edu.aast.rtdms.sahi framestats`, 60 s on Live with the mock Pi running | ≤ 5 % janky frames; no bar above the 16 ms line during state changes |
| D2 | Re-renders per poll | `scripts/render-count.mjs` (web) or React DevTools profiler (dev build) with `npm run mock -- --freeze 92` | metric groups render 0× while values do not change |
| D3 | Reduce motion | Settings → Accessibility → *Remove animations* | no press scale, no `max` pulse; color changes and progress bars remain |
| D4 | Driving lock | demo mode, wait for the scenario speed > 10 km/h | only state, speed, hold-to-SOS visible; unlocks below 7 km/h |
| D6 | Pairing | scan the Pi QR (or a test QR `WIFI:T:WPA;S:test;P:pw;U:http://<laptop>:8080;;`) | system "connect to device" prompt, then Live shows data; mobile data still works |
| D7 | Pi offline / reconnect | stop the mock, wait 2 s, start it again | banner within ~1 s of the 3rd failed poll; recovers without a tap |
| D8 | Alerts with the screen off | mock running, lock the phone | notification + voice + vibration on each escalation |
| D9 | Background crash detection | demo mode, lock the phone, wait 2 min, unlock: "Monitoring this trip" notification present; `adb logcat` shows motion batches | the foreground service survived |
| D10 | SOS end to end | demo → Settings → Simulate a crash; let it run out with a **test contact** and `emergencyNumber` set to a test number in code | parallel WhatsApp relay + link-free SMS dispatched; live status updates per contact; call starts; incident logged with outcome "Help requested" |
| D11 | Calibration | mock Pi, Settings → Calibrate eyes | 10 s / 3 s steps, voice says "close your eyes", "Calibrated" at the end |
| D12 | Delete all data | Settings → Delete all data | app restarts at consent; trips, contacts gone |

## 4. Manual crash tests still to do (cannot be automated)

| # | Test | Setup | Pass |
|---|---|---|---|
| M1 | **Drop test** | demo mode (speed faked by the scenario: wait until it shows > 20 km/h), phone in a padded box, drop from ~1 m onto a cushion | countdown appears within ~6 s of the drop (impact + speed "0" from GPS is not faked in demo: use the *Simulate a crash* path to check the countdown, and the drop to check the 4 g spike in `adb logcat`) |
| M2 | **False alarms, speed bumps** | phone in a dash mount, ≥ 30 min of city driving over bumps | 0 countdowns |
| M3 | **False alarms, hard braking** | empty road, 50 → 0 km/h hard stops ×10 | 0 countdowns (braking stays far below 4 g; the stop alone never triggers) |
| M4 | **Loose phone** | phone on the seat, hard braking | may spike: documented limit, the spec requires a mount |
| M5 | **Real Pi endpoints** | once `phone/incident-buffer` exists: crash in demo → clip appears in Trips → plays, downloads | 25 s clip, timeline aligned with 0 s at the impact |

## 5. Pi side (`phone/incident-buffer`, not built yet)

Ring-buffer and endpoint cost must be measured **with all models running on the Pi**, with
`vcgencmd get_throttled` checked before and after (`.cursor/rules/pi-performance-pipeline.mdc`).
