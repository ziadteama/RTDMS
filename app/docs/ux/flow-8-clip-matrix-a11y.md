# Flow 8, state matrix and accessibility

Part of [Sahi UX redesign](../UX.md).

### Flow 8: Incident Clip Consent & Local Sandboxing

#### Goal
Prevent inadvertent sharing or leaking of sensitive in-cabin driver video and telemetry. Ensure that all accident clips and sensor timeline logs remain strictly sandboxed on the phone's internal storage by default. Require an explicit, granular consent disclosure sheet before any video or sensor file can be passed to the Android Sharesheet or exported outside Sahi's sandbox.

#### Trigger
- Tapping "Share clip" or "Export data" on an Incident Screen (`/incident/[id]`).
- Initiating an external file export of an incident bundle.

#### Screen Wireframe: Pre-Share Consent Disclosure Sheet (360dp Wide)

```
+------------------------------------+ 360dp
| [1] ============================== | Sheet handle
| [2] Share Incident Clip?           | type: title (28/34 700)
|     Review details before sharing  | type: caption (13/18 400), textSec
+------------------------------------+
| [3] WHAT THIS CLIP CONTAINS        | Section
| +--------------------------------+ | surface: #14171A
| | In-Cabin Video (25 seconds)    | | Row
| | Driver face, upper body, and   | | type: body (17/24 400)
| | passenger cabin recording.     | | type: caption (13/18 400)
| | (15s before impact, 10s after) | |
| |--------------------------------| | separator: #2A2F35
| | Vehicle & Impact Telemetry     | | Row
| | GPS location: 30.0444, 31.2357 | |
| | Impact force: 4.2 g            | |
| | Speed at impact: 52 km/h       | |
| | Heart rate: 84 bpm             | |
| +--------------------------------+ |
|                                    |
| [4] DESTINATION & ACCESS           | Section
| +--------------------------------+ | surface: #14171A
| | Handed to Android Sharesheet   | | Row
| | You choose the receiving app   | |
| | (e.g., messaging, email, drive)| |
| | Sahi has no cloud copy.        | |
| +--------------------------------+ |
|                                    |
| [5] [      SHARE CLIP & DATA       ] | Button: primary, action (48dp)
| [6] [    CANCEL (KEEP ON PHONE)    ] | Button: secondary (48dp)
+------------------------------------+
```

#### Exact Copy Strings (English Only)
- Sheet Title: `"Share Incident Clip?"`
- Sheet Subtitle: `"Review the contents of this export before sharing outside Sahi."`
- Section 1 Header: `"What this clip contains"`
- Video Item Title: `"In-cabin video (25 seconds)"`
- Video Item Detail: `"Contains facial video of the driver and cabin interior recorded 15 seconds before impact and 10 seconds after."`
- Telemetry Item Title: `"Sensor and vehicle telemetry"`
- Telemetry Item Detail: `"Contains GPS location coordinates, peak g impact force, speed timeline, and heart rate."`
- Section 2 Header: `"Destination"`
- Destination Detail: `"Exports to your chosen Android app via system Sharesheet. File is not uploaded to any Sahi cloud server."`
- Confirm Action: `"Share clip & data"`
- Cancel Action: `"Cancel (Keep on phone)"`

#### Default Policy & Technical Boundaries
- **Default State**: Kept on phone. Dismissing the sheet, tapping Cancel, or pressing Android back leaves the clip untouched in `Paths.document/incidents/{id}.mp4`.
- **System Intent**: Once confirmed, invoke `expo-sharing` or native Android `Intent.ACTION_SEND` targeting only the selected file URI with standard temporary read permissions (`FLAG_GRANT_READ_URI_PERMISSION`).

#### Accessibility
- **Touch Target**: Primary "Share clip & data" and secondary "Cancel" buttons each satisfy `minHeight: touch.min` (48dp).
- **TalkBack**: Role `"dialog"`. Reads: `"Share incident clip? Contains in-cabin video of driver face and vehicle telemetry. Double tap Share Clip to proceed, or Cancel to keep on phone."`
- **Reduce Motion**: Bottom sheet fades in using `motion.fast` (150ms opacity transition) rather than vertical translation under reduce motion.

#### i18n Keys (en.ts additions)
```typescript
'clip.consent.title': 'Share Incident Clip?',
'clip.consent.subtitle': 'Review details before sharing outside this phone.',
'clip.consent.contents': 'What this clip contains',
'clip.consent.videoTitle': 'In-cabin video (25 s)',
'clip.consent.videoDetail': 'Driver face, upper body, and cabin recording (15 s before, 10 s after).',
'clip.consent.telemetryTitle': 'Sensor & vehicle telemetry',
'clip.consent.telemetryDetail': 'GPS location, 4.2 g impact peak, speed timeline, and heart rate.',
'clip.consent.destination': 'Destination',
'clip.consent.destinationDetail': 'Sent directly to the Android app you select. Sahi has no cloud server.',
'clip.consent.btnShare': 'Share clip & data',
'clip.consent.btnCancel': 'Cancel (Keep on phone)',
```

---

## 3. UI State Matrix Across Redesigned Flows

Every screen and component in Sahi strictly accounts for empty, error, and offline conditions:

| Flow / Component | Empty State | Error State | Offline State (No Pi / No Network) |
|---|---|---|---|
| **1. Permissions** | All items undetermined: shows "Needed" with secondary Fix buttons. | System intent fails to launch: displays modal guidance instructions. | N/A (local Android OS permissions). |
| **2. Status Pill** | No trip started / Standby: shows "Not armed: Speed 0 km/h". | Sensor error / GPS lost: shows amber "Not armed: No GPS fix". | Pi disconnected: shows neutral "Pi offline" (`surfaceRaised` + `unknown`). |
| **3. False Alert Feedback** | No recent alert: feedback chips hidden from view. | SQLite save failure: gracefully dismisses, logs error to internal console. | Fully operational offline. Feedback saved to local SQLite DB. |
| **4. Per-Alert Why** | No fusion alert reasons present: displays `"live.noReasons"`. | Malformed `/alert` payload: shows raw fallback code or "—". | Displays cached reasons from SQLite trip log for historical review. |
| **5. Emergency SOS** | No emergency contacts registered: skips SMS and routes directly to Stage 2 call. | SMS transmit failure: logs failure and immediately escalates to dialing. | SOS functions without Pi or Wi-Fi (uses phone cellular and GPS). |
| **6. Camera Warning** | Camera clear: warning banner completely hidden. | Camera covered / misaligned: displays high-priority warning banner. | Pi offline: displays "Pi offline" banner rather than false obstruction alert. |
| **7. Score & Streaks** | Trip < 30 s: displays "—" (not enough driving to calculate score). | Corrupted trip telemetry: displays uncalculated state, excludes from weekly average. | Fully calculated and rendered offline on the phone. |
| **8. Clip Consent** | Incident has no video on Pi: shows `"incident.notOnPi"` banner. | Clip download failure: shows error badge with "Retry download" option. | Clip sharing operates locally if clip was previously saved on phone. |

---

## 4. Accessibility & Inclusive Design Verification

- **Touch Targets**: Every actionable element (buttons, rows, chips, toggles) has a minimum physical bounding box of **48dp x 48dp** (`touch.min`). Critical in-vehicle controls provide **64dp** (`touch.large`) or **96dp** (`touch.huge` for "I'm OK").
- **Contrast Ratios (WCAG AAA Compliance)**:
  - Text on neutral background: `#F1F3F5` on `#0B0D0F` (contrast ratio 17.5:1).
  - Secondary text: `#A5ADB5` on `#0B0D0F` (contrast ratio 8.2:1).
  - Alert text: `#06140C` on `#3FB97A` (`alert.none`, ratio 11.2:1); `#1A1402` on `#E3C14B` (`alert.short_beep`, ratio 10.8:1); `#FFFFFF` on `#EF5148` (`alert.continuous`, ratio 4.6:1); `#FFFFFF` on `#FF2E3A` (`alert.max`, ratio 5.1:1).
- **TalkBack & Screen Readers**:
  - All icons provide `accessibilityElementsHidden={true}` and rely on parent container labels.
  - Interactive rows declare `accessibilityRole="button"` and `accessibilityState={{ disabled: boolean }}`.
  - SOS countdown uses `accessibilityLiveRegion="assertive"`. Status pill uses `accessibilityLiveRegion="polite"`.
- **System Reduced Motion**:
  - In-app animations respect the Android OS `useReducedMotion()` setting.
  - Pulsing indicators (`alert.max`) disable opacity oscillation.
  - Button press transitions eliminate 3% scale contraction and replace it with a 30% opacity dim (`opacity: 0.7`).
  - SOS progress bar advances in 1-second discrete steps rather than fluid linear interpolation.
