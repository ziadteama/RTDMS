# Flow 2: monitoring status

Part of [Sahi UX redesign](../UX.md).

### Flow 2: Monitoring Status & System Tray Notification

#### Goal
Provide immediate, unambiguous status of system arming, unit connection, and background health across all app screens and in the Android system tray. Ensure silent OEM kills or user pauses are instantly caught and can be resumed with a single tap.

#### Trigger
- Persistent in top navigation bar across all tabs (`Drive`, `Trips`, `Settings`).
- System-wide foreground service notification.
- "Monitoring paused" push notification posted when sensor stream stalls or app is resumed from an OEM background freeze.

#### Screen Wireframe: Status Pill Variants (ASCII Specification)

```
[ State: ARMED / MONITORING ]
+---------------------------------------+
|  (*) ARMED · 45 km/h                  | bg: alert.none (#3FB97A)
+---------------------------------------+ text: onAlert.none (#06140C)
                                          type: label (15/20 600)

[ State: NOT ARMED (LOW SPEED) ]
+---------------------------------------+
|  (i) NOT ARMED: SPEED < 20 km/h       | bg: alert.short_beep (#E3C14B)
+---------------------------------------+ text: onAlert.short_beep (#1A1402)
                                          type: label (15/20 600)

[ State: NOT ARMED (NO GPS) ]
+---------------------------------------+
|  (!) NOT ARMED: NO GPS                | bg: alert.short_beep (#E3C14B)
+---------------------------------------+ text: onAlert.short_beep (#1A1402)
                                          type: label (15/20 600)

[ State: PAUSED ]
+---------------------------------------+
|  (||) MONITORING PAUSED               | bg: surfaceRaised (#1C2024)
+---------------------------------------+ text: textSecondary (#A5ADB5)
                                          type: label (15/20 600)

[ State: UNIT NOT CONNECTED ]
+---------------------------------------+
|  (x) UNIT NOT CONNECTED               | bg: surfaceRaised (#1C2024)
+---------------------------------------+ text: unknown (#6F7881)
                                          type: label (15/20 600)
```

#### Screen Wireframe: Drive Dashboard Header with Integrated Pill (360dp Wide)

```
+------------------------------------+ 360dp
| Sahi            [ (*) ARMED ]      | Header: label (15/20 600)
|                                    | Pill: alert.none, radius.sm (8)
+------------------------------------+ touch target: 48dp height
| [1] DRIVER STATE                   | StateIndicator
| +--------------------------------+ | bg: alert.none (#3FB97A)
| |                                | |
| |          Attentive             | | type: state (44/52 800)
| |          No alert              | | type: headline (20/26 600)
| |                                | |
| +--------------------------------+ |
|                                    |
| [2] TRIP CONTEXT                   | Context line
| +--------------------------------+ | surface: #14171A
| | Speed: 45 km/h   Trip: 32 min   | | type: metricSmall (20/26 tabular)
| +--------------------------------+ |
|                                    |
| [3] [      HOLD FOR SOS (2s)     ] | HoldButton: touch.large (64dp)
+------------------------------------+
```

#### Screen Wireframe: Status Explanation Sheet (Tapping the Status Pill)

Tapping the status pill opens a plain-language explanation sheet. It does NOT open a diagnostics screen. Diagnostics live strictly in the hidden Diagnostics screen (Settings -> About -> tap version 7 times).

```
+------------------------------------+ 360dp
| [1] ============================== | Sheet handle
| [2] Monitoring Status              | type: title (28/34 700)
|     Current safety protection      | type: caption (13/18 400), textSec
+------------------------------------+
| [3] STATUS EXPLANATION             | Section
| +--------------------------------+ | surface: #14171A
| | Sahi stopped monitoring at     | | type: body (17/24 400)
| | 14:32 because your phone       | |
| | closed it. Tap to fix.         | |
| +--------------------------------+ |
|                                    |
| [4] [      RESUME MONITORING       ] | Button: primary, action (48dp)
| [5] [             DISMISS          ] | Button: ghost (48dp)
+------------------------------------+
```

#### Screen Wireframe: System Tray Persistent Notification

```
+-------------------------------------------------------------+
| (Eye Icon) Sahi · Monitoring Active · now                    |
| Sahi is monitoring this trip                                |
| Armed · Unit connected · Speed 45 km/h · Crash detection on |
+-------------------------------------------------------------+
```

#### Screen Wireframe: "Monitoring Paused" Notification (OEM Kill Recovery)

```
+-------------------------------------------------------------+
| (!) Sahi · System Alert · now                               |
| Monitoring paused                                           |
| Sahi stopped monitoring at 14:32 because your phone closed   |
| it. Tap to fix.                                             |
| [ RESUME MONITORING ]                                       |
+-------------------------------------------------------------+
```

#### Exact Copy Strings (English Only)
- Pill States:
  - Armed: `"Armed"` or `"Armed · {speed} {unit}"`
  - Low speed: `"Not armed: Speed < 20 km/h"`
  - No GPS: `"Not armed: No GPS"`
  - Missing permission: `"Not armed: Setup needed"`
  - Paused: `"Monitoring paused"`
  - Unit not connected: `"Unit not connected"`
- Status Explanation Sheet:
  - Title: `"Monitoring status"`
  - Subtitle: `"Current safety protection"`
  - State Explanations:
    - Armed: `"Sahi is actively monitoring. Your Sahi unit is connected and crash detection is on."`
    - Low speed: `"Crash detection arms automatically once driving above 20 km/h."`
    - No GPS: `"Waiting for GPS fix. Crash detection is disarmed until GPS signal is acquired."`
    - Setup needed: `"Safety permissions need to be completed before monitoring can arm."`
    - Paused: `"Sahi stopped monitoring at {time} because your phone closed it. Tap to fix."`
    - Unit not connected: `"Unit not connected. Check it is powered on."`
  - Action Resume: `"Resume monitoring"`
  - Action Dismiss: `"Dismiss"`
- Persistent Notification:
  - Channel: `service` (NotificationManager.IMPORTANCE_LOW, ongoing).
  - Title: `"Sahi is monitoring this trip"`
  - Body Armed: `"Armed · Unit connected · {speed} {unit} · Crash detection on"`
  - Body Not Armed: `"Unit connected · Crash detection disarmed ({reason})"`
- Paused Notification:
  - Channel: `alerts` (NotificationManager.IMPORTANCE_HIGH).
  - Title: `"Monitoring paused"`
  - Body: `"Sahi stopped monitoring at {time} because your phone closed it. Tap to fix."`
  - Action Label: `"Resume"`

#### State & Token Mapping Table

| Logical State | Trigger / Conditions | Pill Background Token | Text Color Token | Left Icon |
|---|---|---|---|---|
| **Armed** | Unit online, Bluetooth active, GPS fix valid, Speed > 20 km/h (or forced armed) | `colors.alert.none` (`#3FB97A` / `#1C8A52`) | `colors.onAlert.none` (`#06140C` / `#FFFFFF`) | `check` / `dot` |
| **Not Armed: Speed** | Unit online, Speed <= 20 km/h (crash detector speed floor) | `colors.alert.short_beep` (`#E3C14B` / `#8C6F00`) | `colors.onAlert.short_beep` (`#1A1402` / `#FFFFFF`) | `info` |
| **Not Armed: GPS** | Unit online, no GPS lock for > 10 s | `colors.alert.short_beep` (`#E3C14B` / `#8C6F00`) | `colors.onAlert.short_beep` (`#1A1402` / `#FFFFFF`) | `gps` |
| **Paused** | `useSettings.paused === true` or phone closed background service | `colors.surfaceRaised` (`#1C2024` / `#ECEEF0`) | `colors.textSecondary` (`#A5ADB5` / `#4D555D`) | `pause` |
| **Unit Not Connected** | 3 consecutive connection timeouts | `colors.surfaceRaised` (`#1C2024` / `#ECEEF0`) | `colors.unknown` (`#6F7881` / `#79828B`) | `wifiOff` |

#### Accessibility
- **Touch Target**: The status pill serves as an interactive inspection touchpoint. Tapping it opens a plain-language explanation sheet describing the current state. Minimum touch bounding box: 48dp x 48dp via `hitSlop: 12`.
- **TalkBack**: Role `"status"`. Live region `"polite"`. Label: `"Monitoring status: Armed, driving at 45 kilometers per hour. Double tap for status details."`
- **Engineering Diagnostics Isolation**: System diagnostics are strictly located in the hidden Diagnostics screen (Settings -> About -> tap version 7 times), never accessed from the status pill.
- **Reduce Motion**: Color transitions respect `motion.base` (250ms ease-out) without bouncy scale springs. Pulses are disabled.

#### i18n Keys (en.ts additions)
```typescript
'status.pill.armed': 'Armed',
'status.pill.armedSpeed': 'Armed · {speed} {unit}',
'status.pill.notArmedSpeed': 'Not armed: Low speed',
'status.pill.notArmedGps': 'Not armed: No GPS',
'status.pill.notArmedPerm': 'Not armed: Setup needed',
'status.pill.paused': 'Monitoring paused',
'status.pill.offline': 'Unit not connected',
'status.sheet.title': 'Monitoring status',
'status.sheet.subtitle': 'Current safety protection',
'status.sheet.armed': 'Sahi is actively monitoring. Your Sahi unit is connected and crash detection is on.',
'status.sheet.notArmedSpeed': 'Crash detection arms automatically once driving above 20 km/h.',
'status.sheet.notArmedGps': 'Waiting for GPS fix. Crash detection is disarmed until GPS signal is acquired.',
'status.sheet.notArmedPerm': 'Safety permissions need to be completed before monitoring can arm.',
'status.sheet.paused': 'Sahi stopped monitoring at {time} because your phone closed it. Tap to fix.',
'status.sheet.offline': 'Unit not connected. Check it is powered on.',
'status.sheet.resume': 'Resume monitoring',
'status.sheet.dismiss': 'Dismiss',
'service.notif.armed': 'Armed · Unit connected · {speed} {unit}',
'service.notif.disarmed': 'Unit connected · Disarmed ({reason})',
'service.notif.pausedTitle': 'Monitoring paused',
'service.notif.pausedBody': 'Sahi stopped monitoring at {time} because your phone closed it. Tap to fix.',
'service.notif.resume': 'Resume',
```

---
