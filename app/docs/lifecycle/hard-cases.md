# Lifecycle hard cases

Part of [Sahi lifecycle](../LIFECYCLE.md).

## 4. Hard Cases & Technical Implementations

### 4.1 OEM Kill Detection Without a Push Service (realme GT 6T / ColorOS & Reference Devices)

#### 4.1.1 The Constraint Environment
- Primary Worked Target: realme GT 6T (`RMX3853`), running Android 16 (SDK 36) with ColorOS:
  - Google Play Services vs. Zero-Cloud Policy: Although Google Play services are present on the realme GT 6T test phone, Sahi enforces a strict local-only boundary and **never assumes GMS in code**. The app relies on zero Google APIs, zero cloud servers, and zero Firebase Cloud Messaging (FCM) endpoints for background keep-alive or wakeups.
  - ColorOS Process Reclamation: ColorOS implements aggressive background process management ("Allow background activity" toggles, "Auto-launch" controls, intelligent background freezing, and deep sleep optimizations). Even when running a valid Android foreground service with a visible ongoing notification and wake lock, ColorOS may terminate the application process via an uncatchable `SIGKILL` if background power consumption thresholds are exceeded or under system memory pressure.
  - Android 16 (SDK 36) Behavior: Android 16 introduces refined background execution constraints and stricter foreground service management. Its exact interaction with ColorOS process killing policies is **unverified, test on device**.
  - Termination Impact: When killed by ColorOS via `SIGKILL`:
    - No Kotlin, Android lifecycle, or React Native callbacks execute (`onDestroy()` is completely bypassed).
    - No BLE disconnection packet or graceful GATT termination is sent.
    - The phone process terminates silently without the ability to post a notification or wake an in-process alarm.
- Reference / Returning Target: Huawei Y9a (`FRL-L22`):
  - Operating System: Android 10 with EMUI 10.1, MediaTek Helio G80.
  - Constraint: Pure HMS device with no GMS, no Google Play services, and no FCM. Proprietary EMUI PowerGenie terminates background apps aggressively via `SIGKILL`. Since this phone may return to active testing, the architecture guarantees seamless operation on pure HMS/AOSP environments.
- Generic No-GMS Device Baseline:
  - Pure AOSP and de-Googled distributions (e.g. GrapheneOS, LineageOS without microG).
  - Devices lack any push architecture; process reclamation is managed strictly by the Android Low Memory Killer (LMK) and vendor battery managers. The app must detect kills entirely locally without external push assistance.

#### 4.1.2 Proposed Heartbeat Watchdog Mechanism
To detect ungraceful terminations locally without any cloud or push service (and without assuming GMS):
1. Heartbeat Writer: While monitoring is active (in `driving` or foreground service running), the foreground service writes a monotonic timestamp to a lightweight storage target (SQLite WAL or memory-mapped KV file) every N seconds:
   $$\text{HEARTBEAT\_INTERVAL\_MS} = 5000 \text{ (5 seconds)}$$
2. Startup Inspection: On every process launch (`app/src/app/index.tsx` or `BootReceiver`), the application reads:
   - `last_heartbeat_timestamp`
   - `last_known_monitoring_state` (`active` or `paused`)
   - `open_trip_id` (via `db.openTrip()`)
3. Kill Condition Evaluation:
   $$\text{isOemKill} = (\text{last\_state} == \text{'active'}) \land (\text{open\_trip} \neq \text{null}) \land (t_{\text{current}} - t_{\text{heartbeat}} > 30000)$$
4. User Notification and Resumption:
   - Calculate gap window: from $t_{\text{heartbeat}}$ to $t_{\text{current}}$.
   - Format timestamps into local time ($HH:MM$).
   - Display persistent UI Banner on Drive and Trips screens:
     `"Sahi stopped monitoring at 14:32 because your phone closed it. Tap to fix."`
   - Post local notification via `SahiNative.notify` (channel `alerts`):
     `"Sahi stopped monitoring at 14:32 because your phone closed it. Tap to fix."`
   - Retroactively close the stale trip in SQLite:
     $$\text{endedAt} = \text{stale.startedAt} + (\text{stale.summary.onlineS} \times 1000)$$

#### 4.1.3 Detectability Boundary Matrix

| Parameter / Event | Primary: realme GT 6T (ColorOS, Android 16, GMS present*) | Reference: Huawei Y9a (EMUI 10.1, Android 10, HMS only) | Generic No-GMS Device (AOSP / De-Googled) | Technical Reason & Detection Strategy |
|---|---|---|---|---|
| Process termination occurrence | YES *(unverified, test on device)* | YES | YES | Evaluated retroactively on subsequent startup via heartbeat timestamp gap > 30 s in SQLite/KV. |
| Time of termination | YES | YES | YES | Known within $\pm 5\text{ s}$ (timestamp of last successful heartbeat write before `SIGKILL`). |
| Duration of monitoring gap | YES | YES | YES | Delta between last heartbeat timestamp and next process initialization timestamp ($\Delta t = t_{\text{current}} - t_{\text{heartbeat}}$). |
| Device reboot during gap | YES *(unverified, test on device)* | YES | YES | Detectable by comparing system boot time (`SystemClock.elapsedRealtime()`) against heartbeat timestamp. |
| Exact instant of kill while dead | NO | NO | NO | Process is dead; no code execution possible on device without an external server or push engine (GMS push bypassed by architectural zero-cloud policy). |
| Specific OEM subsystem that issued kill | NO | NO | NO | OS kernel does not record whether ColorOS background freezer, EMUI PowerGenie, or standard LMK issued `SIGKILL` in user-accessible storage without root/logcat. |
| In-cab events during the dead gap | NO on phone | NO on phone | NO on phone | Phone sensors were unpowered. (Pi hardware recorded independent events locally, but phone could not trigger SOS escalation). |
| Kill if app is never opened again | NO *(unverified, test on device)* | NO | NO | Without user launch or OS broadcast delivery (`BOOT_COMPLETED`), no code ever runs to evaluate the heartbeat gap. |

*\*Note: Google Play services are present on the realme GT 6T test device, but never assumed or used in code (zero-cloud boundary). Android 16 behaviors are unverified, test on device.*

---

### 4.2 Independent Phone-Only Crash Detection and Arming State

> [!NOTE] Engineering note: Decoupling phone-only sensing from unit connectivity.

#### 4.2.1 Removal of Unit-Online Dependency
In the current codebase (`app/src/services/monitor.ts` lines 60-68):
```typescript
function isArmed(): boolean {
  const live = useLive.getState();
  const { crashDetection } = useSettings.getState();
  return (
    crashDetection &&
    live.connection === 'online' &&
    recentSpeeds.some((s) => s.kmh > ARM_SPEED_KMH && s.t > Date.now() - 10_000)
  );
}
```
And line 81:
```typescript
if (!useSettings.getState().crashDetection || useLive.getState().connection !== 'online') return;
```
This couples crash detection to the unit connection. If the unit Wi-Fi or BLE link drops, crash detection disarms silently.

[Proposed] Architectural Modification:
Decouple crash detection from `live.connection`. The phone possesses its own calibrated IMU (100 Hz) and GPS receiver. Crash detection must run independently on the phone:
```typescript
// Proposed implementation
function isArmed(): boolean {
  const live = useLive.getState();
  const { crashDetection, paused } = useSettings.getState();
  const hasGpsFix = !gpsLost(live.gpsAt, Date.now());
  const movingFastEnough = recentSpeeds.some((s) => s.kmh > ARM_SPEED_KMH && s.t > Date.now() - 10_000);

  return crashDetection && !paused && hasGpsFix && movingFastEnough;
}
```
Unit data (face lost, heart rate spike) remains optional supporting evidence (`extras()` in `app/src/services/monitor.ts` line 70), but is never a prerequisite for arming or impact detection.

#### 4.2.2 Visible Arming Status Model
The driver must always know why crash detection is or is not armed. A dedicated status element is exposed on the Drive screen:

| Arming State | Visual Presentation | Exact Condition |
|---|---|---|
| **Armed** | Green badge / pill (`#3FB97A`): "Crash detection armed" | Speed was > 20 km/h in last 10 s, GPS fix fresh (< 10 s stale), motion sampling active at 100 Hz, crash detection toggle ON. |
| **Not Armed: Speed** | Amber badge (`#E3C14B`): "Not armed: speed under 20 km/h" | GPS fix valid, but speed has not exceeded 20 km/h in past 10 s (e.g. stationary or slow city traffic). |
| **Not Armed: GPS** | Amber badge (`#E3C14B`): "Not armed: no GPS" | GPS fix stale (> 10 s) or location permission denied (`gpsLost(gpsAt, now) === true`). |
| **Not Armed: Sensors**| Red badge (`#EF5148`): "Not armed: motion sensors unavailable" | Device lacks accelerometer/gyroscope or `sahi-native` motion thread failed. |
| **Not Armed: Paused** | Neutral grey badge (`#6F7881`): "Not armed: monitoring paused" | Driver explicitly enabled "Pause monitoring" in Settings. |
| **Not Armed: Disabled**| Neutral grey badge (`#6F7881`): "Not armed: disabled in settings"| `crashDetection` toggle set to `false` in Settings. |

---

### 4.3 Device Reboot and Broadcast Lifecycle

#### 4.3.1 `BOOT_COMPLETED` Under Vendor Limits
- Standard Android Behavior: Android sends `android.intent.action.BOOT_COMPLETED` after system startup to all applications that have the `RECEIVE_BOOT_COMPLETED` permission and have been launched at least once.
- realme GT 6T (ColorOS / Android 16 SDK 36):
  - ColorOS manages boot and background startup through its "Auto-launch" / "Startup manager" feature. Sideloaded or user apps may have boot startup disabled by default or subject to battery optimization profiles. (Android 16 SDK 36 boot broadcast delivery under ColorOS: unverified, test on device).
  - Required User Action (Onboarding Checklist for realme / ColorOS):
    1. Navigate to: `Settings -> Apps -> App management -> Sahi -> Battery usage` (or `Settings -> Battery -> More settings -> App battery management -> Sahi`).
    2. Enable `Allow background activity` and `Allow auto-launch`.
    3. Under battery optimization, ensure Sahi is set to `Don't optimize`.
    *(Exact ColorOS settings navigation path on Android 16: unverified, test on device).*
- Huawei EMUI Restriction (Reference for FRL-L22):
  - Huawei EMUI disables boot broadcasts for sideloaded or standard applications by default. The system drops the `BOOT_COMPLETED` intent unless the user manually grants launch privileges.
  - Required User Action (Huawei Reference Checklist):
    1. Navigate to: `Settings -> Battery -> App Launch`.
    2. Locate `Sahi` and switch from `Manage automatically` to `Manage manually`.
    3. Ensure all three toggles are enabled:
       - `Auto-launch` (allows app to start on boot).
       - `Secondary launch` (allows app to be woken by other components).
       - `Run in background` (prevents PowerGenie from killing the foreground service).
- Generic No-GMS / AOSP Behavior:
  - Standard AOSP delivers `BOOT_COMPLETED` once the user unlocks the device (credential encrypted storage unlocked), provided the app is not in a force-stopped state.

#### 4.3.2 Boot Recovery Flow
When `BOOT_COMPLETED` is delivered to `SahiBootReceiver`:
1. Database Cleanup: Inspect `sahi.db` for unclosed trips (`endedAt IS NULL`). Close any open trip at its last recorded heartbeat timestamp.
2. Gap Evaluation: Evaluate if a trip was running when power was lost. If yes, record gap in database.
3. Standby Service Launch: If monitoring is not paused and device is paired, start `Location.startLocationUpdatesAsync` in background standby mode.
4. BLE Scan: Begin background BLE scanning for the paired Pi GATT peripheral UUID.

---

### 4.4 Application Update and Migration Lifecycle

#### 4.4.1 Version Transition Detection
On application startup, Sahi compares the active application package `versionCode` against `stored_version_code` stored in SQLite KV-store:
```typescript
const currentVersion = Constants.expoConfig?.android?.versionCode ?? 1;
const storedVersion = kv.getItem('sahi.version_code');
if (!storedVersion || Number(storedVersion) < currentVersion) {
  runUpdateMigrations(Number(storedVersion), currentVersion);
  kv.setItem('sahi.version_code', String(currentVersion));
}
```

#### 4.4.2 Permission and Battery Exemption Audit
Android OS updates or APK reinstalls frequently reset runtime permissions or battery exemption whitelist flags. The update handler triggers an immediate audit:
1. Permissions Check (Android 12+ / 14+ / 16 SDK 36):
   - Location: `Location.getForegroundPermissionsAsync()` (`ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`). *Enforcement*: On Android 14+ and Android 16 (SDK 36), starting a foreground service of type `location` strictly requires while-in-use location permissions to be granted first before service launch (Android 16 enforcement details: unverified, test on device).
   - Bluetooth: `PermissionsAndroid.check('android.permission.BLUETOOTH_SCAN')` and `PermissionsAndroid.check('android.permission.BLUETOOTH_CONNECT')` (required on Android 12+ / SDK 31+).
   - Notifications: `PermissionsAndroid.check(POST_NOTIFICATIONS)` (required on Android 13+ / SDK 33+).
   - SMS & Phone: `PermissionsAndroid.check(SEND_SMS)` and `PermissionsAndroid.check(CALL_PHONE)`.
2. Battery Exemption Check:
   - Call native `PowerManager.isIgnoringBatteryOptimizations(packageName)` to verify exemption from standard Doze mode and ColorOS background restrictions.
3. Resolution UX:
   If any previously granted permission or battery optimization has been revoked, Sahi displays a persistent, non-dismissible banner on the Drive tab:
   `"Safety permissions were reset by system update. Tap to re-enable crash SOS protection."`

#### 4.4.3 SQLite Schema Migrations
Database migrations are handled via SQLite's built-in `user_version` pragma:
```sql
PRAGMA user_version;
```
If `user_version < 2`:
- Run SQL migration statements within a single transaction.
- Example: Create `heartbeat` table, add contract version column to `trips`.
- Update pragma: `PRAGMA user_version = 2;`.

---

### 4.5 Data Deletion, Privacy Boundaries, and Unpairing

#### 4.5.1 Local Storage Erasure Scope
When the driver selects "Delete all data" in Settings -> Privacy and my data (`app/src/screens/settings/index.tsx` line 270):
1. SQLite Database: `db.wipe()` executes:
   ```sql
   DELETE FROM events;
   DELETE FROM hr;
   DELETE FROM incidents;
   DELETE FROM trips;
   ```
2. SecureStore (Android Keystore): `useSecure.getState().wipe()` executes:
   - Erases `sahi.contacts` (all emergency contact names and phone numbers).
   - Erases `sahi.wifi` (stored unit Wi-Fi SSID and WPA2 passphrase).
   - [Proposed] Erases `sahi.ble` (stored BLE auth token `K` and peripheral identity).
3. KV-Store: `clearKv()` purges all settings, resetting `consentedAt = null` and `onboarded = false`.
4. Process Reload: Invokes `reloadAppAsync('all data deleted')` to restart app into a pristine, unconsented state.

#### 4.5.2 Unit Pairing Token Invalidation and Uninstall Footprint

> [!NOTE] Engineering note: Token rotation and storage residue.

- Uninstall Footprint: When the driver uninstalls Sahi via the Android OS, the OS purges `/data/data/edu.aast.rtdms.sahi`. All local databases, encryption keys, and tokens on the phone are destroyed.
- Unit Residue: The unit has NO user account records and stores no driver personal details. However, the static pairing token `K` remains in the unit configuration file (`contracts/pi-link/CONTRACT.md` line 69), and any incident video clips recorded during trips remain on the unit's internal storage (`incidents/`).
- Token Invalidation Procedure:
  To revoke access from an uninstalled phone, the driver must rotate the pairing token on the unit:
  - Through the unit local setup web page, or
  - Via the unit command-line interface: `rtdms-admin rotate-token`.
  Rotating the token on the unit invalidates all previously paired phones instantly (`contracts/pi-link/CONTRACT.md` line 71).

#### 4.5.3 Zero-Cloud Verification
Sahi contains no network communication code directed outside the vehicle. Even when operating on devices with Google Play services present (such as the realme GT 6T), the application never assumes GMS in code and makes zero network calls to Google or cloud infrastructure:
- Grep validation gate (`app/docs/VALIDATION.md` §1):
  `grep -rnE "fetch\(|https://" src` matches only:
  - `pi/transport.ts` (calls to local unit `10.42.0.1:8080`).
  - Google Maps URL template text generated for the outgoing SMS (`emergency.ts`).
  - Maps linking intent when user taps "Open in Maps".
- Zero telemetry, zero analytics, zero crash reporting SDKs, zero remote push services.

---

### 4.6 Transport Boundary Management: BLE Range and Wi-Fi Scoping

#### 4.6.1 BLE Range Degradation and Recovery
- Out of Range: When the driver walks away from the vehicle:
  - BLE GATT connection is dropped by the Bluetooth controller.
  - Live state transitions: `connection = 'offline'` (`app/src/state/live.ts`).
  - Trip Manager enters the 60 s grace period (`END_AFTER_OFFLINE_MS = 60_000` in `app/src/services/trips.ts`).
- Reconnection in < 60 s: If the driver returns within 60 seconds (e.g. paying for fuel):
  - BLE peripheral re-advertises; phone central re-establishes GATT link.
  - Event logged: `db.addEvent(tripId, now, 'connected', '')`.
  - Trip continues uninterrupted in the same database session.
- Disconnected > 60 s: Trip Manager finalizes the trip, records `endedAt`, and computes the safety score. Subsequent connection begins a new trip.

#### 4.6.2 Wi-Fi Hotspot Demand Scoping

> [!NOTE] Engineering note: Scoped Wi-Fi connection handling.

The unit's Wi-Fi hotspot has NO internet connectivity. If an Android device remains bound to a no-internet Wi-Fi network, Android routing policies may drop cellular data or fail to route emergency SMS/calls.
- Binding Policy:
  Sahi joins and binds to the unit Wi-Fi network (`sahi-native` `joinWifi`) EXCLUSIVELY during active video sessions:
  1. When actively running setup or the Calibrate screen (`app/src/app/calibrate.tsx`) while parked (live camera video is never streamed on the Drive tab while driving).
  2. When downloading an incident MP4 clip (`app/src/app/incident/[id].tsx`).
- Immediate Unbinding:
  As soon as the driver leaves setup/calibration, locks the screen, or vehicle speed exceeds 10 km/h (driving lock engaged), the application immediately invokes:
  ```kotlin
  // SahiNativeModule.kt line 130
  cm.bindProcessToNetwork(null)
  ```
  This returns standard network routing to the cellular interface immediately, ensuring cellular SMS and emergency calling are uninhibited.

#### 4.6.3 Unit Contract Version Mismatch Handling
When connecting via BLE, Sahi reads the `health` characteristic `0x0a` or parses the pairing QR field `V:<version>`:
- If `health.contract !== APP_CONTRACT_VERSION`:
  1. The app displays a non-blocking warning banner:
     `"Unit software mismatch (Unit vX, App vY). Basic monitoring active; advanced features disabled."`
  2. The app DOES NOT guess, interpolate, or synthesize changed payloads.
  3. Compatible GATT characteristics (`alert` on `0x01`, `incident` on `0x07`) continue to operate.
  4. Features depending on altered or unsupported characteristics are disabled in the UI (showing "—").
  5. Phone-side crash detection remains fully armed and autonomous.

---
