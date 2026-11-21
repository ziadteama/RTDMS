# Lifecycle states 9-16: trip end to data deletion

Part of [Sahi lifecycle](../LIFECYCLE.md).

### State 9: `trip end`
- Entry Trigger: BLE connection remains disconnected for > 60 continuous seconds (`END_AFTER_OFFLINE_MS = 60_000` in `app/src/services/trips.ts` line 14) OR user toggles "Pause monitoring" in Settings.
- Exit Trigger: Final trip summary and safety score saved in SQLite; transitions to `idle`.
- Execution Matrix:
  - Foreground Service: Stopped via `Location.stopLocationUpdatesAsync(LOCATION_TASK)` (`app/src/services/monitor.ts` line 165).
  - BLE Connection: Disconnected or idling in background scanner.
  - GPS: Stopped.
  - IMU 100 Hz: Stopped via `SahiNative.stopMotion()` (`app/src/services/monitor.ts` line 161).
  - Poller / Transport: Suspended.
  - Wi-Fi Station: Unbound.
- User Experience:
  - Screen: Driving lock disengages; Live tab returns to unlocked idle view; Trips tab shows newly completed trip card with safety score (0–100), alert breakdown, and duration.
  - Notification: Ongoing foreground service notification is dismissed.
  - Status Pill: Shows "Offline" or "Paused".
- Failure Handling: If trip ends abruptly with 0 duration, short-trip safety score floor applies (`app/src/trips/score.ts`).
- Persistence:
  - SQLite: `db.saveTrip(tripId, { endedAt: at, summary, score: safetyScore(summary) })` executed (`app/src/services/trips.ts` line 48).
  - Trip ID set to `null`.

### State 10: `backgrounded`
- Entry Trigger: User minimizes Sahi, switches to navigation/audio app, or locks the device screen while a trip is running.
- Exit Trigger: User brings Sahi back to the foreground (`AppState` transitions to `active`).
- Execution Matrix:
  - Foreground Service: ACTIVE. `FOREGROUND_SERVICE_LOCATION` holds background execution priority.
  - BLE Connection: ACTIVE. GATT notifications processed in background.
  - GPS: ACTIVE. Background location updates delivered to `LOCATION_TASK`.
  - IMU 100 Hz: ACTIVE. Native `SensorEventListener` on `HandlerThread` continues sampling uninterrupted.
  - Poller / Transport: Active via BLE notify handlers.
  - Wi-Fi Station: Unbound.
- User Experience:
  - Screen: Device homescreen or alternative user-facing application.
  - Notification:
    - Persistent notification: "Sahi is monitoring this trip".
    - On Alert Escalation: High-priority heads-up notification with vibration and `expo-speech` voice cue (`app/src/services/alerts.ts`).
    - On Crash / Impact: Full-screen intent notification on channel `sos` waking the display and opening `/sos` countdown (`SahiNativeModule.kt` line 106).
  - Status Pill: Not visible until app is reopened.
- Failure Handling: Android OS low-memory killer will reclaim background activities; the foreground service protects the process from standard low-memory drops.
- Persistence:
  - Continues 10 s SQLite trip summaries and 5 s heartbeat writes.

### State 11: `killed by OEM battery manager`
- Entry Trigger: OEM process killer (ColorOS background task killer / process freezer on realme GT 6T, or EMUI PowerGenie on Huawei FRL-L22) kills the process via uncatchable `SIGKILL` due to high sensor/CPU usage or aggressive power management, bypassing standard Android foreground service guarantees (Android 16 ColorOS kill behavior: unverified, test on device).
- Exit Trigger: Driver re-launches Sahi manually from the launcher icon (or system auto-launches via `BOOT_COMPLETED` if configured).
- Execution Matrix:
  - Foreground Service: TERMINATED abruptly. Notification removed by OS.
  - BLE Connection: TERMINATED (socket closed by OS).
  - GPS: TERMINATED.
  - IMU 100 Hz: TERMINATED.
  - Poller / Transport: TERMINATED.
  - Wi-Fi Station: TERMINATED.
- User Experience:
  - While Killed: Phone is inert. IN-CAB MONITORING CONTINUES ON PI (camera, fusion, and buzzer run independently).
  - On Next App Launch:
    - Screen: Banner appears at the top of Live and Trips screens: "Monitoring was paused from HH:MM to HH:MM (closed by phone battery manager)".
    - Notification: Local notification posted: "Monitoring was interrupted: Sahi was stopped by battery manager. Check auto-launch and background activity settings."
    - Status Pill: Warning banner active.
- Failure Handling:
  - Detection: [Proposed] Heartbeat inspection. On startup, app reads `last_heartbeat` timestamp from KV-store/SQLite. If `currentTime - last_heartbeat > 30 s` and an unclosed trip exists, app detects ungraceful OEM kill.
  - Recovery: `app/src/services/trips.ts` lines 26-30 closes the stale trip using `stale.startedAt + stale.summary.onlineS * 1000`. A new trip record begins cleanly when conditions are met.
- Persistence:
  - SQLite: Stale trip row updated with computed `endedAt`. Event logged: `kind: 'oem_kill'`.

### State 12: `device reboot`
- Entry Trigger: Phone powers down, battery exhausts, or system restarts.
- Exit Trigger: Operating system finishes booting and broadcasts `android.intent.action.BOOT_COMPLETED`.
- Execution Matrix:
  - Foreground Service: Inactive until BootReceiver runs.
  - BLE Connection: Inactive until initialized.
  - GPS: Inactive until initialized.
  - IMU 100 Hz: Inactive until initialized.
  - Poller / Transport: Inactive.
  - Wi-Fi Station: Inactive.
- User Experience:
  - Screen: Device lock screen.
  - Notification: If auto-launch allowed by ColorOS / EMUI, ongoing notification appears: "Sahi is waiting for vehicle connection". If blocked by OEM power management, no notification appears until user manually opens Sahi (Android 16 boot notification behavior: unverified, test on device).
  - Status Pill: None until app opened.
- Failure Handling:
  - On realme GT 6T (ColorOS, Android 16), `BOOT_COMPLETED` reception depends on ColorOS "Auto-launch" toggle being enabled in App Management / Battery settings (Android 16 delivery: unverified, test on device).
  - On Huawei FRL-L22 (EMUI 10.1), `BOOT_COMPLETED` is discarded by default unless the driver has manually enabled "Auto-launch" in EMUI Battery settings.
  - If not enabled, monitoring remains inactive until the next manual app tap.
- Persistence:
  - On startup: Unclosed trips from before the reboot are closed in SQLite (`app/src/services/trips.ts`).

### State 13: `app update`
- Entry Trigger: Sahi package updated (e.g. newer APK installed via sideload), triggering `android.intent.action.MY_PACKAGE_REPLACED`.
- Exit Trigger: Migration checks and permission audits complete; app ready for use.
- Execution Matrix:
  - Foreground Service: Inactive during update.
  - BLE Connection: Inactive.
  - GPS: Inactive.
  - IMU 100 Hz: Inactive.
  - Poller / Transport: Inactive.
  - Wi-Fi Station: Inactive.
- User Experience:
  - Screen: Normal launch. If Android revoked permissions during update, a warning banner is shown: "Permissions reset by update. Tap to re-enable."
  - Notification: None.
  - Status Pill: Normal.
- Failure Handling:
  - Permission Re-Audit: Checks `PermissionsAndroid.check()` for location (`ACCESS_FINE_LOCATION`, verifying while-in-use location before foreground service), Bluetooth (`BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT` on Android 12+), notifications (`POST_NOTIFICATIONS` on Android 13+), SMS, and call.
  - Battery Re-Audit: Checks `PowerManager.isIgnoringBatteryOptimizations()`.
  - Database Schema: Checks `PRAGMA user_version` in SQLite; executes incremental migration SQL scripts before mounting UI.
- Persistence:
  - SQLite KV-Store: Updates `last_version_code` to new package `versionCode`.
  - SQLite: Updates `PRAGMA user_version`.

### State 14: `Pi contract version mismatch`
- Entry Trigger: BLE connection established and `health.contract` (from GATT characteristic `0x0a` or pairing QR) does not equal the app's contract version (`contracts/pi-link/CONTRACT.md` line 73).
- Exit Trigger: Pi firmware updated, app updated, or unit unpaired.
- Execution Matrix:
  - Foreground Service: Active if trip running.
  - BLE Connection: Active. Connects to compatible characteristics only.
  - GPS: Active on phone.
  - IMU 100 Hz: Active on phone.
  - Poller / Transport: Active for compatible endpoints; drops unknown/mismatched payloads.
  - Wi-Fi Station: Inactive unless supported video requested.
- User Experience:
  - Screen: Persistent banner at the top of Live and Pi tabs: "Pi software mismatch: basic monitoring active; advanced features disabled."
  - Notification: None.
  - Status Pill: Amber warning pill. Missing data fields display "—", never 0 or fake values (`app/docs/API.md` line 130).
- Failure Handling: App keeps compatible parts; never guesses missing or changed payload shapes. Safety monitoring on the phone (crash SOS) remains fully functional.
- Persistence:
  - Memory: Mismatch flag set in `useLive`. No corrupt schemas written to SQLite.

### State 15: `unpair`
- Entry Trigger: Driver taps "Unpair Pi" in Settings (`app/src/screens/settings/index.tsx`).
- Exit Trigger: Stored credentials purged; app returns to unpaired state.
- Execution Matrix:
  - Foreground Service: Stopped if active.
  - BLE Connection: Disconnected; auto-reconnect disabled; BLE bond dropped.
  - GPS: Stopped if in trip.
  - IMU 100 Hz: Stopped.
  - Poller / Transport: Terminated.
  - Wi-Fi Station: Unbound and forgotten.
- User Experience:
  - Screen: Confirmation dialog, then routes to Settings/Home. Modal informs driver: "Phone unpaired. To invalidate this phone on the Pi, rotate the pairing token on the Pi setup page."
  - Notification: None.
  - Status Pill: "Unpaired".
- Failure Handling: If Pi is offline when unpair is selected, phone removes local credentials immediately; driver is advised to rotate the token on the Pi manually.
- Persistence:
  - SecureStore (`app/src/state/secure.ts`): `wifi` credentials set to `null`; [Proposed] `sahi.ble` token set to `null`.
  - KV-Store: `baseUrl` reset to `http://10.42.0.1:8080`.
  - SQLite: Historical trips and incidents retained.

### State 16: `uninstall and data deletion`
- Entry Trigger:
  - Data Deletion: User taps "Delete all data" in Settings -> Privacy (`app/src/screens/settings/index.tsx` line 270).
  - Uninstall: User uninstalls package via Android OS settings or launcher.
- Exit Trigger:
  - Data Deletion: Storage wiped; app restarts into Consent flow via `reloadAppAsync`.
  - Uninstall: Application package directory deleted by Android OS.
- Execution Matrix:
  - Foreground Service: Destroyed.
  - BLE Connection: Terminated.
  - GPS: Terminated.
  - IMU 100 Hz: Terminated.
  - Poller / Transport: Terminated.
  - Wi-Fi Station: Unbound.
- User Experience:
  - Data Deletion: Native alert prompt: "Delete all data? This deletes every trip, incident, and setting from this phone. This cannot be undone." On confirmation, screen reloads to `/consent`.
  - Uninstall: System confirmation dialog; app removed from device.
  - Status Pill: None.
- Failure Handling: If database deletion fails, files are removed directly from disk via filesystem API.
- Persistence:
  - Local Storage Erasure (`app/src/screens/settings/index.tsx` lines 277-281):
    - `db.wipe()`: Clears `events`, `hr`, `incidents`, `trips` (`app/src/state/db.ts` line 124).
    - `useSecure.getState().wipe()`: Clears `contacts` and `wifi` from Android Keystore (`app/src/state/secure.ts` line 52).
    - `useSettings.getState().reset()`: Resets settings store.
    - `clearKv()`: Purges SQLite KV-store (`app/src/state/storage.ts` line 11).
  - Pi-Side Residue: No user data exists on the Pi except its static auth token `K` and any video clips stored on the Pi's local storage (`incidents/`). Uninstalling leaves nothing on the Pi except that token. Token rotation on the Pi severs all future access.
  - Cloud: Zero data in cloud (no cloud infrastructure exists).

---
