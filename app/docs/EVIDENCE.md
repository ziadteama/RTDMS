# What has actually been measured

Everything below was run on **2026-11-20** in a Linux x86-64 cloud container (4 vCPU, 15 GB RAM,
Node 22.23.5, JDK 17 + 21). **No phone, emulator or Raspberry Pi was available** to that machine.
Anything a phone or the Pi must show is listed under "Not measured" with the check that will
measure it ([VALIDATION.md](VALIDATION.md)). Re-run the commands; do not cite these numbers after
the code changes without re-running them.

## Gates

| Gate | Command | Result |
|---|---|---|
| Types | `npx tsc --noEmit` (TypeScript 6.0.3, strict + `noUncheckedIndexedAccess`) | 0 errors |
| Lint | `npx eslint .` (eslint-config-expo, React Compiler rules) | 0 problems |
| Tests | `npm test` | 6 suites, **55 / 55 passed**, 0 skipped (real-recording suite ran: `.data/` present) |
| Expo doctor | `NODE_USE_ENV_PROXY=1 npx expo-doctor` (1.21.8) | **20/20 checks passed** |
| Android build | `npx expo prebuild -p android` + `./gradlew assembleDebug -PreactNativeArchitectures=arm64-v8a` | **BUILD SUCCESSFUL in 5 m 50 s** (AGP 9.2.1, Gradle 9.4.1, Kotlin 2.2; `sahi-native` compiled with no warnings). `app-debug.apk` 104.7 MB (debug dev client, arm64-v8a only, unminified): package `edu.aast.rtdms.sahi` 0.1.0, compileSdk 37, targetSdk 36, `expo.modules.sahinative` classes present |

Merged permissions in that APK (`aapt2 dump badging`): location (fine / coarse), `FOREGROUND_SERVICE` + `_LOCATION`,
`CAMERA`, `SEND_SMS`, `CALL_PHONE`, `POST_NOTIFICATIONS`, `USE_FULL_SCREEN_INTENT`, `VIBRATE`,
`WAKE_LOCK`, network / Wi-Fi state; added by libraries: `RECEIVE_BOOT_COMPLETED` (task manager),
`USE_BIOMETRIC` / `USE_FINGERPRINT` (secure-store, never prompted); debug-only from the dev client:
`SYSTEM_ALERT_WINDOW`, `CHANGE_WIFI_MULTICAST_STATE`, `ACCESS_LOCAL_NETWORK`. Blocked on purpose:
`RECORD_AUDIO`, `ACCESS_BACKGROUND_LOCATION`, external storage.

Build environment notes (container only, not app configuration): the egress proxy rate-limits
`repo.maven.apache.org` (HTTP 429, which makes Gradle drop the repository), so a machine-local
`~/.gradle/init.d` script pointed Maven Central at Google's mirror
(`maven-central.storage-download.googleapis.com`); Gradle's JDK 17 toolchain came from apt because
toolchain download (foojay) was blocked; Node's `fetch` needs `NODE_USE_ENV_PROXY=1` behind the proxy.

## Crash detector (`src/crash/detector.test.ts`, 24 tests)

| Case | Data | Result |
|---|---|---|
| Spike + stop → event | 6 g spike at 60 km/h, GPS 0 after 1 s | event at the spike, 6.0 g, speed before 60 |
| Spike, no speed drop | 6 g, GPS stays 60 | none |
| Below 20 km/h | 6 g at 15 km/h, then 0 | none |
| < 4 g with a stop | 3.2 g, then 0 | none |
| Stop too late / does not hold | stop at +6 s; stop then 30 km/h | none / none |
| Waits for GPS | only 2 s of GPS after the stop → none; 5 s → event | as expected |
| Synthetic normal drive | 20 min, 100 Hz, bumps up to 2.5 g, hard braking 0.8 g, stops at lights | **0 events** |
| Same + injected impact | 5, 6, 7, 8 g, car above 35 km/h | **4 / 4 detected**, within 100 ms of the injection, flip detected |
| **Real recordings, worst case** | driverBehaviorDataset (Ferreira et al., PLOS ONE 2017): 4 trips, 51.3 min, mounted Motorola XT1058, ~51 Hz, incl. aggressive braking / acceleration / turns / lane changes. Assumed armed throughout and a GPS stop right after the strongest spike | **0 events in 4 / 4 trips** |
| Real recording + injected impact | trip 16 + 5, 6, 7, 8 g | **4 / 4 detected** |

Peak |a| (gravity included) in the real recordings: trip 16 **2.11 g**, 17 **1.44 g**,
20 **2.47 g**, 21 **2.24 g** (99.9th percentile 1.26–1.77 g). The 4 g threshold sits 1.6× above
the hardest real manoeuvre in the data. These are 51 min of one car and two drivers on dry roads;
they say nothing yet about potholes, speed bumps at speed or a loose phone (manual tests M2–M4).

## Re-renders on the 5 Hz poll (`node scripts/render-count.mjs 10`)

Web build (Chromium, React 19.3 dev, React Compiler on), Live tab, 10 s, the mock Pi on the same
machine. Counts are component re-renders after mount (a minimal React DevTools hook; a fiber
counts only when it re-ran with new props or state).

| Mock | `/status` polls | Commits | Live | Banners | State | Video / LiveView | Eyes | Heart | Phone | SOS button | Metric |
|---|---|---|---|---|---|---|---|---|---|---|---|
| frozen (`--freeze 92`, values constant) | 50 | **0** | 0 | 0 | 0 | 0 / 0 | 0 | 0 | 0 | 0 | 0 |
| running (values change every poll) | 50 | 79 | 0 | 0 | 1 | 0 / 0 | 50 | 10 | 1 | 0 | 135 |

Reading: a poll that changes nothing re-renders nothing; when values change only the group that
shows them re-renders (eye metrics at 5 Hz, heart at 1 Hz, state once on a phase change), and the
WebView live view never re-renders.

> [!note] Methodology correction
> The first version of the counter read React's `PerformedWork` flag alone and reported
> `StateIndicator` and `LiveView` re-rendering on every poll while their parents did not. Fibers in a
> bailed-out subtree are not cloned and keep stale flags, so those were false counts. The counter now
> also requires new props or hook state since it last saw that fiber; both rows above are from the
> corrected counter.

## Bundle (`npx expo export -p android`)

Hermes bytecode bundle **4.70 MB** (production, minified); assets 1.2 MB, of which 976 KB is the
Material Symbols font that `expo-symbols` bundles for offline icons and 76 KB the demo-mode clip.
Not yet done for release: R8 / resource shrinking (`android.enableMinifyInReleaseBuilds`) and a
release APK size.

## Screenshots

`app/docs/screenshots/{dark,light}-{en,ar}/*.png`: 15 screens × 4 = 60 images, produced by
`node scripts/screenshots.mjs` against `npm run mock -- --freeze 92` and `expo start --web`,
390 × 844 pt at 2×. They are **web renders** of the same code: the Android tab bar (NativeTabs)
is drawn by a web stand-in, `@expo/ui` controls are their web versions (on web the RTL slider draws
its fill from the left; Android uses Compose in an RTL host), and there is no camera on web (QR
screen shows the manual-address path). The live view shows the mock's placeholder frames.

## Not measured (and how it will be)

| Item | Why not | Check |
|---|---|---|
| 60 fps on a mid-range Android | no device / emulator (no KVM) on the build machine | VALIDATION D1 (`dumpsys gfxinfo`, release build) |
| App running on a phone at all (native module at runtime, permissions, foreground service, SMS / call) | no device | VALIDATION D6–D12 |
| Crash detector on real crashes / real false-alarm rate | only replayed data so far | VALIDATION M1–M4 |
| Talking to the real Pi | no Pi reachable; its proposed endpoints are not built | VALIDATION M5 once `phone/incident-buffer` exists |
| Pi ring-buffer CPU / RAM cost | **not measured on target** (not built) | `phone/incident-buffer`, with all models running, `vcgencmd get_throttled` before / after |
| Arabic voice (`ar-EG`) | depends on the phone's installed TTS voices | VALIDATION D5 / D8 on the phone |
