# Flows 6 and 7: calibration warning, score and streaks

Part of [Sahi UX redesign](../UX.md).

### Flow 6: Calibration Lost / Camera Covered Warning

#### Goal
Detect and warn the driver immediately when the camera on your Sahi unit is obstructed, smudged, or knocked out of alignment with the driver's face. Prevent false confidence in driver monitoring when the system is actually blind.

#### Trigger
- Your Sahi unit detects loss of eye/face tracking while the vehicle is in motion ($v > 10\text{ km/h}$) due to lens obstruction or physical misalignment.
- Contract Change Proposal: Status payload includes `tracking_status` flag.

#### Proposed Contract Change Request (Candidate for contracts/pi-link/CONTRACT.md)
> [!NOTE] Engineering note: Proposed Contract Change Request (Candidate for contracts/pi-link/CONTRACT.md)
> Propose augmenting the `status` notification schema (`schemas/status.schema.json` and `PiDrowsiness`):
> ```json
> {
>   "drowsiness": {
>     "camera_covered": true,
>     "calibration_valid": false,
>     "obstruction_level": "blocked"
>   }
> }
> ```
> *Field values*: `obstruction_level: "clear" | "smudged" | "blocked" | "misaligned"`.

#### Screen Wireframe: Drive Screen with Warning Banner (360dp Wide)

```
+------------------------------------+ 360dp
| Sahi            [ (!) NOT ARMED ]  | Header
+------------------------------------+
| [1] CRITICAL WARNING BANNER        | WarningBanner variant
| +--------------------------------+ | bg: surfaceRaised (#1C2024)
| |[!] CAMERA OBSTRUCTED           | | accent bar: alert.continuous
| |    Lens is covered or blocked  | | type: label (15/20 600)
| |    Monitoring is suspended     | | type: caption (13/18 400)
| |    [ FIX CAMERA ]              | | Button: secondary (48dp)
| +--------------------------------+ |
|                                    |
| [2] DRIVER STATE                   | StateIndicator
| +--------------------------------+ | bg: surfaceRaised (#1C2024)
| |        Face not visible        | | type: state (44/52 800)
| |        Camera obstructed       | | type: headline (20/26 600)
| +--------------------------------+ |
|                                    |
| [3] TRIP CONTEXT                   | Context line
| +--------------------------------+ | surface: #14171A
| | Speed: 45 km/h   Trip: 32 min   | | type: metricSmall (20/26 tabular)
| +--------------------------------+ |
|                                    |
| [4] [      HOLD FOR SOS (2s)     ] | HoldButton (64dp)
+------------------------------------+
```

#### Screen Wireframe: Camera Recovery & Re-calibration Sheet (360dp Wide)

```
+------------------------------------+ 360dp
| [1] ============================== | Sheet handle
| [2] Restore Camera Monitoring      | type: title (28/34 700)
|     Follow these steps while parked| type: caption (13/18 400), textSec
+------------------------------------+
| [3] RECOVERY CHECKLIST             | Section
| +--------------------------------+ | surface: #14171A
| | 1. Check Camera Lens           | | Row
| |    Wipe dust, fingerprints, or | | type: body (17/24 400)
| |    items hanging from mirror.  | | type: caption (13/18 400)
| |--------------------------------| | separator: #2A2F35
| | 2. Adjust Camera Angle         | | Row
| |    Ensure windshield mount is  | |
| |    aimed directly at face.     | |
| |--------------------------------| |
| | 3. Set Up Driving Position     | | Row
| |    Position face with preview  | |
| |    then calibrate while parked.| |
| +--------------------------------+ |
|                                    |
| [4] [   SET UP DRIVING POSITION    ] | Button: primary, action (48dp)
| [5] [             DISMISS            ] | Button: ghost (48dp)
+------------------------------------+
```

#### Exact Copy Strings (English Only)
- Banner Title: `"Camera obstructed"` or `"Driving position lost"`
- Banner Detail: `"Clear lens or adjust angle to resume driver monitoring."`
- Banner Action: `"Fix camera"`
- System Notification (when backgrounded):
  - Title: `"Camera tracking lost"`
  - Body: `"Sahi cannot see driver face. Adjust camera mount to restore protection."`
- Recovery Sheet Title: `"Restore Camera Monitoring"`
- Recovery Steps:
  - `"1. Inspect lens: Clean dust, smudges, or hanging mirror obstructions."`
  - `"2. Adjust angle: Ensure the camera mount points squarely at driver eye level."`
  - `"3. Set up driving position: Run the 13-second eye calibration while safely parked."`
- Action Buttons: `"Set up driving position"`, `"Dismiss"`

#### Accessibility
- **Touch Target**: The banner Fix button has `minHeight: touch.min` (48dp).
- **TalkBack**: Notification and banner trigger an assertive announcement: `"Warning: Camera obstructed. Monitoring is suspended. Double tap Fix camera for recovery steps."`
- **Reduce Motion**: Accent bar maintains solid `alert.continuous` color without blinking or pulsing.

#### i18n Keys (en.ts additions)
```typescript
'warning.camera.coveredTitle': 'Camera obstructed',
'warning.camera.coveredDetail': 'Lens is covered or blocked. Monitoring is suspended.',
'warning.camera.calLostTitle': 'Driving position lost',
'warning.camera.calLostDetail': 'Driver position has shifted. Set up driving position to restore accuracy.',
'warning.camera.btnFix': 'Fix camera',
'warning.camera.sheetTitle': 'Restore Camera Monitoring',
'warning.camera.sheetSubtitle': 'Perform these recovery steps while safely parked.',
'warning.camera.step1Title': 'Inspect camera lens',
'warning.camera.step1Detail': 'Wipe off dust, smudges, or items hanging from your rearview mirror.',
'warning.camera.step2Title': 'Adjust camera angle',
'warning.camera.step2Detail': 'Aim the mount directly at your normal driving head position.',
'warning.camera.step3Title': 'Set up driving position',
'warning.camera.step3Detail': 'Takes 13 seconds parked. Establishes fresh eye baselines.',
'warning.camera.btnCalibrate': 'Set up driving position',
```

---

### Flow 7: Score Transparency & Positive Streaks

#### Goal
Eliminate driver anxiety and resentment caused by mysterious safety scores (a major complaint identified in fleet and commercial DMS studies). Publish the exact mathematical formula and point weights from `app/src/trips/score.ts`. Guarantee driver-only data sovereignty (no cloud sync, no employer or insurer access, no punitive discipline). Motivate attentiveness with positive streaks.

#### Trigger
- Tapping the "Safety Score" card or weekly graph on the Trips screen (`/trips`).
- Tapping "How score is calculated" link in Trip Details (`/trip/[id]`).

#### Screen Wireframe: Score Transparency & Streaks (360dp Wide)

```
+------------------------------------+ 360dp
| [1] How Your Score Works           | type: title (28/34 700)
|     Transparent · Private · Local  | type: caption (13/18 400), textSec
+------------------------------------+
| [2] ATTENTIVENESS STREAKS          | Section
| +--------------------------------+ | surface: #14171A
| | Attentive Driving Streak       | | Row
| | 54 minutes clean               | | metricSmall: 20/26 tabular
| | No drowsiness or distraction   | | caption: (13/18 400), textSec
| |--------------------------------| | separator: #2A2F35
| | Clean Trips Streak             | | Row
| | 4 consecutive trips            | | metricSmall: 20/26 tabular
| | Zero repeated or severe alerts | |
| +--------------------------------+ |
|                                    |
| [3] EXACT SCORE FORMULA            | Section
| +--------------------------------+ | surface: #14171A
| | Score = 100 × e^(-rate / 40)   | | Code block: headline
| |                                | | tabular-nums
| | Rate = (Points + Phone/10) / H | |
| | • Short beep:       1 point    | | Grouped list: body (17/24)
| | • Repeated alarm:   3 points   | |
| | • Continuous alarm: 4 points   | |
| | • Maximum alarm:    8 points   | |
| | • Phone usage:      1 pt / 10s | |
| |                                | |
| | Rules:                         | | caption: textSecondary
| | • Trips < 30s: Not scored      | |
| | • Trips < 10m: Counted as 10m  | |
| +--------------------------------+ |
|                                    |
| [4] DRIVER-ONLY PRIVACY PROMISE    | Section
| +--------------------------------+ | surface: #14171A
| | Strictly Private to You        | | Row
| | Scores are calculated locally  | | type: body (17/24 400)
| | and never sent to cloud servers| | tone: secondary
| | insurers, or employers.        | |
| +--------------------------------+ |
|                                    |
| [5] [          CLOSE EXPLANATION     ] | Button: secondary (48dp)
+------------------------------------+
```

#### Exact Copy Strings (English Only)
- Screen Title: `"How Your Score Works"`
- Header Subtitle: `"Transparent · Private to you · Positive reinforcement"`
- Streaks Section: `"Attentiveness streaks"`
- Clean Minutes Label: `"Attentive driving streak"`
- Clean Minutes Value: `"{n} minutes clean"`
- Clean Trips Label: `"Clean trips streak"`
- Clean Trips Value: `"{n} consecutive trips"`
- Streaks Explanatory Note: `"Clean time counts driving without distraction, phone use, or drowsiness alerts."`
- Formula Section Header: `"Scoring calculation"`
- Formula Narrative:
  - `"Your score starts at 100 and scales from 0 to 100 based on alert frequency normalized per hour of driving."`
  - `"Points per alert onset: Short beep = 1 pt, Repeated alarm = 3 pts, Continuous alarm = 4 pts, Maximum alarm = 8 pts."`
  - `"Phone penalty: 1 penalty point per 10 seconds of detected phone use."`
  - `"Fairness safeguards: Drives under 30 seconds are not scored. Short trips under 10 minutes are calculated as 10 minutes so a single early beep does not destroy your score."`
- Privacy Section Header: `"Driver-only privacy guarantee"`
- Privacy Body: `"Your trip scores exist only in this phone's encrypted SQLite database. Sahi has no cloud backend, no user accounts, and no data sharing. Your driving score cannot be used by employers, insurers, or fleet managers for pay, discipline, or premium adjustments."`

#### Implementation Alignment with `app/src/trips/score.ts`
- Verified: Point weights match `WEIGHTS = { short_beep: 1, repeated: 3, continuous: 4, max: 8 }`.
- Verified: Phone points divisor is `s.phoneMs / 10_000`.
- Verified: Hours floor is `Math.max(s.onlineS / 3600, 1 / 6)`.
- Verified: Score formula is `Math.round(100 * Math.exp(-points / hours / 40))`.

#### Accessibility
- **Touch Target**: The Close button has `minHeight: touch.min` (48dp). Grouped rows support full-row selection.
- **TalkBack**: Role `"article"`. Reads structured text cleanly without symbol confusion: `"How your score works. Attentive driving streak: 54 minutes clean. Clean trips streak: 4 consecutive trips. Double tap Close to return."`
- **Reduce Motion**: Static data layout without moving progress graphs or counters.

#### i18n Keys (en.ts additions)
```typescript
'score.how.title': 'How Your Score Works',
'score.how.subtitle': 'Transparent, private to you, and designed for safety.',
'score.how.streaks': 'Attentiveness streaks',
'score.how.cleanMinutes': 'Attentive driving streak',
'score.how.cleanMinutesVal': '{n} minutes clean',
'score.how.cleanTrips': 'Clean trips streak',
'score.how.cleanTripsVal': '{n} consecutive trips',
'score.how.streaksDetail': 'Driving without distraction, phone use, or drowsiness alerts.',
'score.how.formulaTitle': 'Score calculation',
'score.how.formulaBody': 'Score starts at 100 and adjusts exponentially based on alert frequency per hour.',
'score.how.weights': 'Alert points: Short beep (1), Repeated (3), Continuous (4), Maximum (8). Phone use: 1 pt per 10 seconds.',
'score.how.safeguards': 'Fairness safeguards: Drives under 30 s are not scored. Drives under 10 min use a 10 min minimum divisor.',
'score.how.privacyTitle': 'Driver-only privacy guarantee',
'score.how.privacyBody': 'Stored on this phone only. Never uploaded to the cloud, never shared with insurers, employers, or fleet managers.',
```

---
