# Flow 2: monitoring status

Part of [Sahi UX redesign](../UX.md).

### Flow 2: Monitoring Status & System Tray Notification

#### Goal
Provide immediate, unambiguous status of system arming, Pi connection, and background health across all app screens and in the Android system tray. Ensure silent OEM kills or user pauses are instantly caught and can be resumed with a single tap.

#### Trigger
- Persistent in top navigation bar across all tabs (`Live`, `Trips`, `Pi`, `Settings`).
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
|  (!) NOT ARMED: NO GPS FIX            | bg: alert.short_beep (#E3C14B)
+---------------------------------------+ text: onAlert.short_beep (#1A1402)
                                          type: label (15/20 600)

[ State: PAUSED ]
+---------------------------------------+
|  (||) MONITORING PAUSED               | bg: surfaceRaised (#1C2024)
+---------------------------------------+ text: textSecondary (#A5ADB5)
                                          type: label (15/20 600)

[ State: PI OFFLINE ]
+---------------------------------------+
|  (x) PI OFFLINE                       | bg: surfaceRaised (#1C2024)
+---------------------------------------+ text: unknown (#6F7881)
                                          type: label (15/20 600)
```

#### Screen Wireframe: Live Dashboard Header with Integrated Pill (360dp Wide)

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
| [2] CAMERA VIEW                    | LiveView container
| +--------------------------------+ | surface: #14171A
| | [      CABIN VIDEO FEED      ] | | aspect: 4:3
| |                                | |
| +--------------------------------+ |
|                                    |
| [3] TELEMETRY                      | Grouped Metrics
| +--------------------------------+ | surface: #14171A
| | Speed: 45 km/h   HR: 72 bpm    | | type: metricSmall (20/26 tabular)
| +--------------------------------+ |
|                                    |
| [4] [      HOLD FOR SOS (2s)     ] | HoldButton: touch.large (64dp)
+------------------------------------+
```

#### Screen Wireframe: System Tray Persistent Notification

```
+-------------------------------------------------------------+
| (Eye Icon) Sahi · Monitoring Active · now                    |
| Sahi is monitoring this trip                                |
| Armed · Connected to Pi · Speed 45 km/h · Crash detection ON|
+-------------------------------------------------------------+
```

#### Screen Wireframe: "Monitoring Paused" Notification (OEM Kill Recovery)

```
+-------------------------------------------------------------+
| (!) Sahi · System Alert · now                               |
| Monitoring paused                                           |
| Background service was stopped by Android. Protection is OFF|
| [ RESUME MONITORING ]                                       |
+-------------------------------------------------------------+
```

#### Exact Copy Strings (English Only)
- Pill States:
  - Armed: `"Armed"` or `"Armed · {speed} {unit}"`
  - Low speed: `"Not armed: Speed < 20 km/h"`
  - No GPS: `"Not armed: No GPS fix"`
  - Missing permission: `"Not armed: Missing permission"`
  - Paused: `"Monitoring paused"`
  - Pi offline: `"Pi offline"`
- Persistent Notification:
  - Channel: `service` (NotificationManager.IMPORTANCE_LOW, ongoing).
  - Title: `"Sahi is monitoring this trip"`
  - Body Armed: `"Armed · Pi connected · {speed} {unit} · Crash detection on"`
  - Body Not Armed: `"Connected to Pi · Crash detection disarmed ({reason})"`
- Paused Notification:
  - Channel: `alerts` (NotificationManager.IMPORTANCE_HIGH).
  - Title: `"Monitoring paused"`
  - Body: `"Background tracking was stopped. Driver alerts and crash detection are offline."`
  - Action Label: `"Resume"`

#### State & Token Mapping Table

| Logical State | Trigger / Conditions | Pill Background Token | Text Color Token | Left Icon |
|---|---|---|---|---|
| **Armed** | Pi online, BLE/Wi-Fi active, GPS fix valid, Speed > 20 km/h (or forced armed) | `colors.alert.none` (`#3FB97A` / `#1C8A52`) | `colors.onAlert.none` (`#06140C` / `#FFFFFF`) | `check` / `dot` |
| **Not Armed: Speed** | Pi online, Speed <= 20 km/h (crash detector speed floor) | `colors.alert.short_beep` (`#E3C14B` / `#8C6F00`) | `colors.onAlert.short_beep` (`#1A1402` / `#FFFFFF`) | `info` |
| **Not Armed: GPS** | Pi online, no GPS lock for > 10 s | `colors.alert.short_beep` (`#E3C14B` / `#8C6F00`) | `colors.onAlert.short_beep` (`#1A1402` / `#FFFFFF`) | `gps` |
| **Paused** | `useSettings.paused === true` or OEM kill detected | `colors.surfaceRaised` (`#1C2024` / `#ECEEF0`) | `colors.textSecondary` (`#A5ADB5` / `#4D555D`) | `pause` |
| **Pi Offline** | 3 consecutive HTTP/BLE timeouts | `colors.surfaceRaised` (`#1C2024` / `#ECEEF0`) | `colors.unknown` (`#6F7881` / `#79828B`) | `wifiOff` |

#### Accessibility
- **Touch Target**: The status pill serves as an interactive inspection touchpoint. Tapping it opens an diagnostic dialog showing detailed subsystem statuses. Minimum touch bounding box: 48dp x 48dp via `hitSlop: 12`.
- **TalkBack**: Role `"status"`. Live region `"polite"`. Label: `"Monitoring status: Armed, driving at 45 kilometers per hour. Double tap for system diagnostics."`
- **Reduce Motion**: Color transitions respect `motion.base` (250ms ease-out) without bouncy scale springs. Pulses are disabled.

#### i18n Keys (en.ts additions)
```typescript
'status.pill.armed': 'Armed',
'status.pill.armedSpeed': 'Armed · {speed} {unit}',
'status.pill.notArmedSpeed': 'Not armed: Low speed',
'status.pill.notArmedGps': 'Not armed: No GPS',
'status.pill.notArmedPerm': 'Not armed: Setup needed',
'status.pill.paused': 'Monitoring paused',
'status.pill.offline': 'Pi offline',
'status.dialog.title': 'System Diagnostics',
'status.dialog.pi': 'Pi link: {state}',
'status.dialog.gps': 'GPS accuracy: {acc} m',
'status.dialog.speed': 'Current speed: {speed} {unit}',
'status.dialog.crash': 'Crash detection: {state}',
'service.notif.armed': 'Armed · Pi connected · {speed} {unit}',
'service.notif.disarmed': 'Connected · Disarmed ({reason})',
'service.notif.pausedTitle': 'Monitoring paused',
'service.notif.pausedBody': 'Driver monitoring stopped. Tap Resume to protect this drive.',
'service.notif.resume': 'Resume',
```

---
