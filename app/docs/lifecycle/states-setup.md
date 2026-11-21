# Lifecycle states 1-8: install to driving

Part of [Sahi lifecycle](../LIFECYCLE.md).

## 3. Comprehensive State Specifications

### State 1: `install` (First Run)
- Entry Trigger: Initial launch of the application binary following APK sideloading or installation. Evaluated at `app/src/app/index.tsx`.
- Exit Trigger: Settings check identifies `onboarded === false` and `consentedAt === null`, triggering immediate navigation to `/(onboarding)/consent`.
- Execution Matrix:
  - Foreground Service: Inactive.
  - BLE Connection: Inactive.
  - GPS: Inactive.
  - IMU 100 Hz: Inactive.
  - Poller / Transport: Inactive (`useRuntime()` in `app/src/services/runtime.ts` line 32: `if (!onboarded || paused) return;`).
  - Wi-Fi Station: Inactive.
- User Experience:
  - Screen: Splash icon on `#0B0D0F` background (`app/app.json`), transitioning to `/consent`.
  - Notification: None.
  - Status Pill: None.
- Failure Handling: If SQLite database fails to open or schema creation fails (`app/src/state/db.ts`), app halts with a native initialization error.
- Persistence:
  - SQLite: `sahi.db` created with WAL mode; tables `trips`, `events`, `hr`, `incidents` initialized (`app/src/state/db.ts`).
  - KV-Store: Default settings populated (`DEFAULT_SETTINGS` in `app/src/state/settings.ts`).
  - SecureStore: Empty.
  - Memory: `useLive` initialized to `INITIAL_LIVE` (`app/src/state/live.ts`).

### State 2: `consent`
- Entry Trigger: Navigation from index route (`app/src/app/index.tsx`) or direct navigation when `consentedAt === null`.
- Exit Trigger: Driver presses "Agree" (`app/src/app/(onboarding)/consent.tsx`), persisting consent timestamp and navigating to `/permissions`.
- Execution Matrix:
  - Foreground Service: Inactive.
  - BLE Connection: Inactive.
  - GPS: Inactive.
  - IMU 100 Hz: Inactive.
  - Poller / Transport: Inactive.
  - Wi-Fi Station: Inactive.
- User Experience:
  - Screen: English-only `ConsentStatement` (`app/src/screens/consent.tsx`) detailing: what is processed (camera on your Sahi unit, motion/GPS on phone), what is stored locally (events, incidents), what is sent on crash (SMS with Maps link), and what is never done (no cloud, no remote streaming).
  - Notification: None.
  - Status Pill: None.
- Failure Handling: Navigation is blocked until "Agree" is pressed. Exiting the app leaves `consentedAt === null`; subsequent launches return to `/consent`.
- Persistence:
  - KV-Store: `consentedAt` timestamp (ms) written upon tap (`app/src/state/settings.ts`).
  - SQLite: No rows written.

### State 3: `permissions`
- Entry Trigger: Navigation from `/consent` (`app/src/app/(onboarding)/consent.tsx`).
- Exit Trigger: User reviews required permissions and proceeds to `/connect` (`app/src/app/(onboarding)/permissions.tsx`).
- Execution Matrix:
  - Foreground Service: Inactive.
  - BLE Connection: Inactive.
  - GPS: Inactive (audited via `Location.getForegroundPermissionsAsync()`).
  - IMU 100 Hz: Inactive.
  - Poller / Transport: Inactive.
  - Wi-Fi Station: Inactive.
- User Experience:
  - Screen: Permission audit list (`app/src/app/(onboarding)/permissions.tsx`), aligned with Android 12+ and Android 16 (SDK 36) rules:
    - Bluetooth (`BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`): Required on Android 12+ (SDK 31+) for scanning and connecting to your Sahi unit without needing location permissions for BLE.
    - Notifications (`POST_NOTIFICATIONS`): Mandatory runtime permission on Android 13+ (SDK 33+) for alerts and ongoing foreground service notifications.
    - Location (`ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`): Used for vehicle speed gating and emergency SOS coordinates. *Foreground Service Constraint*: Under Android 14+ and Android 16 (SDK 36), starting a foreground service of type `location` strictly requires while-in-use location permissions to be granted *prior* to starting the service (Android 16 enforcement: unverified, test on device).
    - SMS & Phone (`SEND_SMS`, `CALL_PHONE`): Used for automated emergency escalation without tapping.
    - Camera (`CAMERA`): Used once to scan the setup QR code.
    - [Proposed] Background Launch / Battery Exemption: Explains ColorOS "Allow background activity" and "Auto-launch" controls on realme GT 6T (and EMUI manual launch controls on Huawei FRL-L22).
  - Notification: None.
  - Status Pill: Status tag per item ("Granted", "Allow", "Denied", "Unsupported").
- Failure Handling: Denied permissions are permitted to proceed, but degraded runtime behavior is noted (e.g. denied SMS causes SOS to fall back to launching the system dialer/composer; denied while-in-use location prevents starting the location foreground service).
- Persistence:
  - System: Android OS runtime permission records.
  - Storage: No app storage modified.

### State 4: `pairing` (QR, BLE Bond, Token Write, Wi-Fi Creds)
- Entry Trigger: Navigation to `/connect` during onboarding or `/pair` from Settings (`app/src/screens/pair.tsx`).
- Exit Trigger: Successful QR scan, BLE GATT connection, auth token write to characteristic `0x09`, and credential verification.
- Execution Matrix:
  - Foreground Service: Inactive.
  - BLE Connection: [Proposed] BLE central scanning for peripheral matching name or service `0000fff0-0000-1000-8000-00805f9b34fb`. On connect, requests MTU 247 and writes token `K` to `auth` characteristic `0x09` (`contracts/pi-link/CONTRACT.md`).
  - GPS: Inactive.
  - IMU 100 Hz: Inactive.
  - Poller / Transport: Inactive (or checking test endpoint).
  - Wi-Fi Station: In existing code (`app/src/screens/pair.tsx`), uses `SahiNative.joinWifi` to verify HTTP `/status` at `10.42.0.1:8080`. Under the [Proposed] hybrid contract, Wi-Fi credentials are saved to SecureStore and immediately unbound; Wi-Fi is not kept active.
- User Experience:
  - Screen: Viewfinder using `expo-camera` (`CameraView` in `app/src/screens/pair.tsx`), status feedback ("Joining...", "Checking...", "Pairing failed"), and manual URL fallback.
  - Notification: None.
  - Status Pill: Phase indicator ("Busy", "Error", "OK").
- Failure Handling:
  - Invalid QR: Displays "Invalid QR code" (`app/src/screens/pair.tsx` line 59).
  - ATT Authentication Failure: Sahi unit rejects write with insufficient authentication; UI prompts user that the pairing token was refused.
  - Timeout: Prompts user to verify that your Sahi unit is plugged in and Bluetooth is enabled.
- Persistence:
  - SecureStore (`app/src/state/secure.ts`): Writes `sahi.wifi` (`ssid`, `password`), and [Proposed] `sahi.ble` (`token`, peripheral address/UUID).
  - KV-Store: Saves `baseUrl` (`app/src/state/settings.ts`).

### State 5: `calibration`
- Entry Trigger: Driver selects "Set up driving position" from Settings -> Your Sahi unit or taps calibration prompt on Drive screen (`app/src/app/calibrate.tsx`).
- Exit Trigger: Calibration finishes (`result === 'done'`), reports failure (`result === 'failed'`), or user cancels.
- Execution Matrix:
  - Foreground Service: Inactive (unless entered during an active trip while stationary).
  - BLE Connection: Writes calibration command via GATT `command` characteristic `0x05` (or HTTP `POST /calibrate`). Subscribes to `status` notifications to observe `drowsiness.message`.
    > [!NOTE] Engineering note: BLE GATT command characteristic `0x05` triggers calibration on the unit runtime; status notifications deliver intermediate states.
  - GPS: Monitored to confirm vehicle is stationary (speed < 5 km/h).
  - IMU 100 Hz: Running if monitor is active.
  - Poller / Transport: 5 Hz status updates active to monitor calibration progress.
  - Wi-Fi Station: ACTIVE for live camera preview (`/stream.mjpg`) to ensure face is framed within the camera field of view during setup and calibration. Unbound upon exit.
- User Experience:
  - Screen: `Calibrate` screen (`app/src/app/calibrate.tsx`): Camera video preview (`LiveView`), progress bar, Step 1 prompt (10 s eyes open looking ahead), Step 2 prompt (3 s eyes closed), spoken voice lines (`cal.step2`, `cal.done`).
  - Notification: None.
  - Status Pill: "Calibrating", "Calibrated", or failure error message.
- Failure Handling: If face is lost or lighting is insufficient, unit reports `calibration failed: <reason>` in `drowsiness.message`. App speaks failure cue, displays plain-language reason, and presents a "Retry" button.
- Persistence:
  - Unit: Persists baseline face mesh profile in local unit storage.
  - App: Live state updates `drowsiness.calibrated = true`. No local database records created.

### State 6: `idle` (Paired, Not Driving)
- Entry Trigger: Onboarding complete, app open or foreground service active, vehicle speed < 10 km/h, no active trip.
- Exit Trigger: Conjunction of BLE connection established AND vehicle speed > 10 km/h (transitions to `trip auto-start`).
- Execution Matrix:
  - Foreground Service: [Proposed] Low-power background standby receiver or dormant until movement detected.
  - BLE Connection: Reconnection loop active; scans for paired unit peripheral. If connected while parked, receives 5 Hz alert keep-alives and 2 Hz status.
  - GPS: Active in foreground (or low-frequency geofence in background).
  - IMU 100 Hz: Paused or running in low-power mode.
  - Poller / Transport: Listening for BLE notifications if in range.
  - Wi-Fi Station: Disconnected / unbound (`unbindNetwork()` in `SahiNativeModule.kt`).
- User Experience:
  - Screen: Drive tab displaying neutral grey "Unit not connected" (if out of car) or green "Ready" (if sitting in parked car with unit on). Speed shows 0 km/h.
  - Notification: None (or persistent background status if foreground service kept alive).
  - Status Pill: "Unit not connected" or "Ready"; Crash detection indicator displays "Not armed: speed under 20 km/h".
- Failure Handling: Out-of-range BLE advertisements do not generate audible alarms or error banners; the app silently waits.
- Persistence:
  - Memory-only state in `useLive`. No trip rows created.

### State 7: `trip auto-start` (BLE Connected + GPS Speed > Threshold)
- Entry Trigger: Conjunction of authenticated BLE link established AND GPS speed > 10 km/h (`LOCK_KMH = 10`) across 3 consecutive fixes.
  *Implementation Note: Existing code in `app/src/services/trips.ts` line 54 starts a trip immediately upon `connection === 'online'`. [Proposed] requires speed > 10 km/h to prevent creating zero-distance trips while parked.*
- Exit Trigger: Insertion of new trip record into SQLite; transitions to `driving`.
- Execution Matrix:
  - Foreground Service: Started via `Location.startLocationUpdatesAsync(LOCATION_TASK)` with notification "Sahi is monitoring this trip" (`app/src/services/monitor.ts` lines 121-130). Must satisfy Android 14+ / Android 16 foreground service type location prerequisites: while-in-use location (`ACCESS_FINE_LOCATION` or `ACCESS_COARSE_LOCATION`) must already be granted (Android 16 foreground service launch behavior: unverified, test on device).
  - BLE Connection: Connected; writes current wall-clock time (`Date.now()`) to GATT `clock` characteristic `0x08` for ring-buffer synchronization (`contracts/pi-link/CONTRACT.md` line 45).
  - GPS: Best accuracy for navigation, 1 Hz interval.
  - IMU 100 Hz: Started via `SahiNative.startMotion(100)` (`app/src/services/monitor.ts` line 141).
  - Poller / Transport: Subscribed to BLE `alert` (5 Hz), `status` (2 Hz), and `physio` (1 Hz).
  - Wi-Fi Station: Unbound.
- User Experience:
  - Screen: Drive tab updates with active speed and trip timer.
  - Notification: Ongoing notification posted: "Sahi is monitoring this trip" (`t('service.title')`).
  - Status Pill: Connection pill changes to "Armed". Crash indicator updates as speed rises.
- Failure Handling: If SQLite insertion fails, trip sequence is maintained in memory and retried. If BLE drops before speed confirms, trip initialization is aborted.
- Persistence:
  - SQLite: `db.startTrip(now, demo)` executes, generating a new `tripId` (`app/src/state/db.ts` line 67).

### State 8: `driving` (Screen-Off Safe, Driving Lock)
- Entry Trigger: Active trip in progress (`tripId !== null`), speed > 10 km/h (`app/src/screens/live/use-driving-lock.ts`).
- Exit Trigger:
  - Speed drops < 7 km/h: Driving lock releases; remains in `driving` (unlocked).
  - BLE offline > 60 s or manual pause: Transitions to `trip end`.
  - Impact detected (|a| > 4 g followed by stop): Transitions to SOS countdown (`app/src/services/emergency.ts`).
- Execution Matrix:
  - Foreground Service: Running continuously with `FOREGROUND_SERVICE_LOCATION` to hold wake lock and prevent background suspension.
  - BLE Connection: Receiving continuous notifications: `alert` (5 Hz), `status` (2 Hz), `physio` (1 Hz).
  - GPS: Continuous 1 Hz fixes delivered to `TaskManager` task `sahi-location` (`app/src/services/monitor.ts` line 55).
  - IMU 100 Hz: 100 Hz accelerometer and gyroscope sampling on background `HandlerThread("sahi-motion")`. Flushed to JS in 200 ms batches (`SahiNativeModule.kt` line 206). `CrashMonitor` evaluates every 500 ms.
  - Poller / Transport: BLE notification stream active.
  - Wi-Fi Station: STRICTLY UNBOUND. Live camera video is never rendered while driving (component unmounted).
- User Experience:
  - Screen: Driving Lock interface active (`app/src/screens/live/index.tsx` lines 185-197):
    - All tab navigation bars and secondary metrics hidden.
    - Full-screen state indicator colored by `AlertPattern` (green for `none`, amber for `short_beep`, orange for `repeated`, red for `continuous`/`max`).
    - Large digital speed readout.
    - Explanatory caption: "Interface locked while driving".
    - Prominent hold-to-SOS button (`HoldButton`).
  - Screen-Off Safe: If user presses power button, phone screen turns off safely. The foreground service and native sensor thread keep sampling. Full-screen intent only turns screen on for critical SOS events.
  - Notification: Ongoing service notification. Escalated alerts trigger heads-up notifications (channel `alerts`) accompanied by voice lines in English and haptic vibration (`app/src/services/alerts.ts`).
  - Status Pill: Displays driver state ("Alert", "Drowsy", "Distracted", "Phone").
- Failure Handling:
  - Loss of BLE: UI shows neutral grey "Unit not connected"; unit buzzer handles driver alerts; phone continues tracking GPS trip and keeps crash detection armed.
  - Loss of GPS: Crash detection disarms; UI displays banner "No GPS: crash detection is off".
- Persistence:
  - SQLite: Periodic trip summary flush every 10 s (`app/src/services/trips.ts` line 16). Driver state changes written to `events` table; heart rate written to `hr` table every 30 s.
  - [Proposed] Heartbeat: Monotonic timestamp written to SQLite/KV every 5 s.
