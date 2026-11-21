# Flow 1: permission checklist

Part of [Sahi UX redesign](../UX.md).

### Flow 1: Permission Checklist & OEM Background Protection

#### Goal
Ensure 100% of required runtime permissions, foreground-service authorizations, and OEM battery/autostart exemptions are configured before driving. Eliminate silent background termination by OEM task killers (such as ColorOS, MIUI, and One UI) and prevent mid-trip safety monitoring drops. Re-check integrity on every cold start and after every app update.

#### Trigger
- Initial app setup (Onboarding step 2).
- Application cold start if any permission or OEM exemption was revoked.
- Post-app-update (detected via stored `versionCode` bump in SQLite kv-store).
- User navigation via `Settings -> Permissions & Background`.

#### Screen Wireframe: Permission Checklist (360dp Wide, Dark Theme)

```
+------------------------------------+ 360dp
| [1] Permissions & Background       | Navigation Header
|     Required for driver safety     | type: headline (20/26 600)
+------------------------------------+
| [2] CRITICAL PERMISSIONS           | Section Header
| +--------------------------------+ | surface: #14171A
| | [3] Location: Always           | | Row minHeight: 56dp
| |     Speed & crash GPS fix      | | label: body (17/24), text
| |     [ GRANTED ]                | | caption: (13/18), textSec
| |--------------------------------| | status: alert.none (#3FB97A)
| | [4] Notifications              | | separator: #2A2F35
| |     Alerts with screen off     | |
| |     [ GRANTED ]                | |
| |--------------------------------| |
| | [5] SMS & Emergency Calling    | |
| |     Automated crash SOS        | |
| |     [ NEEDED ]         [ FIX ] | | Button: secondary (48dp)
| |--------------------------------| | status: alert.short_beep
| | [6] Nearby Devices (BLE)       | |
| |     Pi telemetry & link        | |
| |     [ GRANTED ]                | |
| |--------------------------------| |
| | [7] Wi-Fi Direct Join          | |
| |     Video clip download        | |
| |     [ GRANTED ]                | |
| |--------------------------------| |
| | [8] Physical Motion            | |
| |     Crash impact detection     | |
| |     [ GRANTED ]                | |
| +--------------------------------+ |
|                                    |
| [9] BACKGROUND RELIABILITY         | Section Header
| +--------------------------------+ | surface: #14171A
| | [10] Battery Exemption         | |
| |      Prevent OS sleep          | |
| |      [ BLOCKED ]       [ FIX ] | | status: alert.continuous
| |--------------------------------| | Button: secondary (48dp)
| | [11] Autostart (ColorOS)       | |
| |      Allow background launch   | |
| |      [ NEEDED ]      [ GUIDE ] | |
| +--------------------------------+ |
|                                    |
| [12] [      CONTINUE TO PAIRING      ] | Button: primary, action
+------------------------------------+ touch.large (64dp)
```

#### Screen Wireframe: Vendor Guidance Sheet (ColorOS / Realme UI)

```
+------------------------------------+ 360dp
| [1] ============================== | Drag handle (scrim overlay)
| [2] Realme / ColorOS Background    | type: title (28/34 700)
|     Keep Sahi active while driving | type: body (17/24), textSec
+------------------------------------+
| +--------------------------------+ | surface: #14171A
| | Step 1: Open Battery Settings  | | Section: grouped steps
| | Tap the button below to open   | | type: body (17/24 400)
| | App Info for Sahi.             | |
| |--------------------------------| | separator: #2A2F35
| | Step 2: Battery Usage          | |
| | Tap 'Battery usage' and enable | |
| | 'Allow background activity'.   | |
| |--------------------------------| |
| | Step 3: Auto-launch            | |
| | Enable 'Allow auto-launch' so  | |
| | Sahi stays armed when phone    | |
| | connects to the Pi in car.     | |
| +--------------------------------+ |
|                                    |
| [3] [      OPEN APP SETTINGS       ] | Button: primary (48dp)
| [4] [      I HAVE COMPLETED THIS   ] | Button: secondary (48dp)
+------------------------------------+
```

#### Exact Copy Strings (English Only)
- Screen Title: `"Permissions & Background"`
- Section Headers: `"Safety permissions"`, `"System reliability"`
- Items & Reasons:
  - Location Always: `"Location (Always)"` / `"Speed gating for driving lock and GPS coordinates for crash SOS."`
  - Notifications: `"Notifications"` / `"High-priority driver alerts and SOS countdown when screen is off."`
  - SMS: `"SMS messaging"` / `"Dispatches emergency text with coordinates to your contacts after a crash."`
  - Phone: `"Phone calls"` / `"Places automated emergency call to dispatch after crash confirmation."`
  - Bluetooth: `"Nearby devices (BLE)"` / `"Connects to RTDMS unit to receive real-time driver state and heart rate."`
  - Wi-Fi: `"Wi-Fi join"` / `"Connects to Pi hotspot to transfer incident video clips and sensor logs."`
  - Motion: `"Physical motion"` / `"100 Hz accelerometer sampling for instant crash impact detection."`
  - Battery Exemption: `"Battery optimization exemption"` / `"Prevents Android from killing Sahi during long drives."`
  - Autostart: `"Autostart & background launch"` / `"Ensures monitoring resumes automatically when paired."`
- Status Indicators: `"Granted"`, `"Needed"`, `"Blocked"`
- Action Buttons: `"Fix"`, `"Guide"`, `"Open settings"`, `"Confirm completed"`, `"Continue"`

#### Vendor-Specific Guidance Matrix
1. **Samsung (One UI)**:
   - Deep Link: `package:com.rtdms.sahi` -> App Info.
   - Textual Steps: `Settings -> Apps -> Sahi -> Battery -> Select 'Unrestricted'`. Next: `Settings -> Device Care -> Battery -> Background usage limits -> Never sleeping apps -> Add Sahi`.
2. **Xiaomi / Redmi / POCO (MIUI / HyperOS)**:
   - Deep Link: Attempt `miui.intent.action.APP_PERM_EDITOR`, fallback to App Info.
   - Textual Steps: `Security app -> Manage apps -> Sahi -> Enable 'Autostart'`. Next: `Battery saver -> Select 'No restrictions'`.
3. **HUAWEI / Honor (EMUI / MagicOS - NO GMS ASSUMED)**:
   - Architecture Rule: Zero dependency on Google Play Services; standalone APK installer checks.
   - Textual Steps: `Optimizer (or Phone Manager) -> App launch -> Find Sahi -> Toggle 'Manage automatically' to OFF -> Enable 'Auto-launch', 'Secondary launch', and 'Run in background'`. Next: `Settings -> Battery -> Protected apps -> Mark Sahi as Protected`.
4. **Oppo / Realme / Vivo (ColorOS / Realme UI / Funtouch)**:
   - Tested on realme GT 6T (ColorOS 15 / Android 16).
   - Deep Link: Application details intent.
   - Textual Steps: `Settings -> Apps -> App management -> Sahi -> Battery usage -> Enable 'Allow background activity' and 'Allow auto-launch'`. Set `App battery management -> Don't optimize`.
5. **OnePlus (OxygenOS)**:
   - Textual Steps: `Settings -> Battery -> Battery optimization -> Sahi -> Select 'Don't optimize'`. Next: `Settings -> Apps -> Auto-launch -> Sahi -> ON`.
6. **Stock Android (Pixel / Motorola / AOSP Android 10-16)**:
   - Deep Link: Direct intent `android.settings.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`.
   - Textual Steps: `Settings -> Apps -> Sahi -> Battery -> Select 'Unrestricted'`. For Android 10+: Select `Location -> Allow all the time`.

#### Technical Lifecycle Verification
- **Cold Start & Resumption**: During `Application.onCreate()` and `AppState.addEventListener('change')`, execute `checkAllPermissions()`. If critical permissions are lost, flag `useLive.getState().armed = false` and display a blocking warning banner.
- **Update Detection**: Compare `PackageInfo.versionCode` against persisted SQLite `kv-store` key `app.last_version_code`. On bump, force-run verification to catch Android runtime permission resets.

#### Accessibility
- **Touch Target**: Every "Fix" / "Guide" button has `minHeight: touch.min` (48dp) and `hitSlop: 8`.
- **TalkBack**: Header accessibilityRole `"header"`. Rows announced as: `"Location Always, permission needed. Speed gating for driving lock and GPS coordinates for crash SOS. Double tap Fix to resolve."`
- **Reduce Motion**: No slide-in transitions. Checklist status updates instantly; button states transition with opacity dim (`0.7`) instead of scale spring.

#### i18n Keys (en.ts additions)
```typescript
'perm.checklist.title': 'Permissions & Background',
'perm.checklist.lead': 'Required for driver safety and continuous in-vehicle protection.',
'perm.sec.safety': 'Safety permissions',
'perm.sec.reliability': 'System reliability',
'perm.location.title': 'Location (Always)',
'perm.location.why': 'Speed gating for driving lock and GPS coordinates for crash SOS.',
'perm.notif.title': 'Notifications',
'perm.notif.why': 'High-priority driver alerts and SOS countdown when screen is off.',
'perm.sms.title': 'SMS messaging',
'perm.sms.why': 'Dispatches emergency text with coordinates to your contacts after a crash.',
'perm.phone.title': 'Phone calls',
'perm.phone.why': 'Places automated emergency call to dispatch after crash confirmation.',
'perm.ble.title': 'Nearby devices (BLE)',
'perm.ble.why': 'Connects to RTDMS unit to receive real-time driver state and heart rate.',
'perm.wifi.title': 'Wi-Fi join',
'perm.wifi.why': 'Connects to Pi hotspot to transfer incident video clips and sensor logs.',
'perm.motion.title': 'Physical motion',
'perm.motion.why': '100 Hz accelerometer sampling for instant crash impact detection.',
'perm.battery.title': 'Battery optimization exemption',
'perm.battery.why': 'Prevents Android from killing Sahi during long drives.',
'perm.autostart.title': 'Autostart & background launch',
'perm.autostart.why': 'Ensures monitoring resumes automatically when paired.',
'perm.status.granted': 'Granted',
'perm.status.needed': 'Needed',
'perm.status.blocked': 'Blocked',
'perm.btn.fix': 'Fix',
'perm.btn.guide': 'Guide',
'perm.btn.continue': 'Continue to pairing',
'perm.vendor.samsung': 'Samsung One UI setup',
'perm.vendor.xiaomi': 'Xiaomi HyperOS / MIUI setup',
'perm.vendor.huawei': 'Huawei setup (No GMS)',
'perm.vendor.realme': 'Realme / ColorOS setup',
'perm.vendor.oneplus': 'OnePlus OxygenOS setup',
'perm.vendor.stock': 'Android system setup',
```

---
