# Flows 3 and 4: wrong-alert feedback and per-alert why

Part of [Sahi UX redesign](../UX.md).

### Flow 3: "This Alert Was Wrong" Feedback

#### Goal
Give the driver immediate, stress-free recourse against false alerts. Collect zero-friction feedback directly on the alert banner, incident review, and SOS countdown screen. Store feedback strictly locally in SQLite to automatically tune driver sensitivity recommendations without uploading personal data.

#### Trigger
- Tapping the "This alert was wrong" feedback chip on the Live alert banner during or immediately following an alert onset.
- Tapping "Report false alert" on an Incident review screen (`/incident/[id]`).
- Tapping "False alarm" on the SOS countdown screen.

#### Screen Wireframe: Live Screen with Alert Banner & Feedback Chip (360dp Wide)

```
+------------------------------------+ 360dp
| Sahi            [ (*) ARMED ]      | Header
+------------------------------------+
| [1] DRIVER STATE BANNER            | StateIndicator
| +--------------------------------+ | bg: alert.repeated (#F08A3C)
| |           Drowsy               | | type: state (44/52 800)
| |       Repeated alarm           | | type: headline (20/26 600)
| |   Why: Long eye closure (2.1s) | | type: body (17/24 400)
| |                                | |
| | [!] THIS ALERT WAS WRONG       | | FeedbackChip (touch.min: 48dp)
| +--------------------------------+ | bg: surfaceRaised (#1C2024)
|                                    | radius: sm (8)
| [2] LIVE CABIN VIEW                | LiveView
| +--------------------------------+ | surface: #14171A
| |                                | |
| |       [ Camera Stream ]        | |
| |                                | |
| +--------------------------------+ |
|                                    |
| [3] TELEMETRY                      |
| +--------------------------------+ |
| | Eyes: 12% open   PERCLOS: 34%  | |
| +--------------------------------+ |
+------------------------------------+
```

#### Screen Wireframe: Feedback Reason Sheet (360dp Wide)

```
+------------------------------------+ 360dp
| [1] ============================== | Sheet handle
| [2] What happened?                 | type: headline (20/26 600)
|     Stored on phone only to tune   | type: caption (13/18 400)
|     your alert sensitivity.        | tone: secondary
+------------------------------------+
| [3] SELECT A REASON                | Section
| +--------------------------------+ | surface: #14171A
| | ( ) Not drowsy                 | | Row minHeight: 48dp
| |--------------------------------| |
| | ( ) Not on phone               | |
| |--------------------------------| |
| | ( ) Looked at side mirror      | |
| |--------------------------------| |
| | ( ) Glare / sunglasses         | |
| |--------------------------------| |
| | ( ) Other reason               | |
| +--------------------------------+ |
|                                    |
| [4] [         SUBMIT FEEDBACK        ] | Button: primary, action (48dp)
| [5] [             DISMISS            ] | Button: ghost (48dp)
+------------------------------------+
```

#### Exact Copy Strings (English Only)
- Trigger Chip: `"[!] This alert was wrong"`
- Sheet Header: `"What happened?"`
- Sheet Subtitle: `"Stored on this phone only to improve sensitivity recommendations. Never shared."`
- Reason Options:
  - `"Not drowsy"`
  - `"Not on phone"`
  - `"Looked at mirror"`
  - `"Sun glare or glasses"`
  - `"Other reason"`
- Confirmation Toast: `"Feedback saved. Sensitivity recommendations updated in Settings."`
- Dismiss Button: `"Dismiss"`
- Submit Button: `"Submit feedback"`

#### Local Data Storage & Sensitivity Tuning (Proposed)
- Schema: Local SQLite table `alert_feedback` (in `state/db.ts`):
  ```sql
  CREATE TABLE alert_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER,
    incident_id INTEGER,
    timestamp INTEGER NOT NULL,
    alert_pattern TEXT NOT NULL,
    primary_reason TEXT NOT NULL,
    user_feedback_reason TEXT NOT NULL
  );
  ```
- **Sensitivity Suggestion Engine**: If a driver logs >= 3 false alarms of type "Not drowsy" within 7 driving days:
  - Settings screen displays a contextual card: *"You flagged 3 drowsiness alerts as incorrect this week. Would you like to adjust eye closure sensitivity from Normal to Low?"*
  - One-tap setting application. Zero network transmission.

#### Accessibility
- **Touch Target**: The feedback chip enforces `minHeight: touch.min` (48dp) with explicit padding `paddingVertical: spacing.sm`, `paddingHorizontal: spacing.md`.
- **TalkBack**: Role `"button"`. Label: `"This alert was wrong. Double tap to report a false alert and tune sensitivity."`
- **Reduce Motion**: Bottom sheet fades in using `motion.fast` (150ms opacity transition) rather than a vertical slide under system reduced motion.

#### i18n Keys (en.ts additions)
```typescript
'feedback.chip': 'This alert was wrong',
'feedback.sheet.title': 'What happened?',
'feedback.sheet.subtitle': 'Stored on phone only to tune sensitivity. Never sent anywhere.',
'feedback.reason.notDrowsy': 'Not drowsy',
'feedback.reason.notPhone': 'Not on phone',
'feedback.reason.mirror': 'Looked at mirror',
'feedback.reason.glare': 'Sun glare or glasses',
'feedback.reason.other': 'Other reason',
'feedback.btn.submit': 'Submit feedback',
'feedback.toast.saved': 'Feedback saved locally.',
'feedback.tuning.suggestTitle': 'Adjust sensitivity?',
'feedback.tuning.suggestDrowsy': 'You reported {count} false drowsiness alerts recently. Switch Drowsiness Sensitivity to Low?',
'feedback.tuning.apply': 'Apply change',
```

---

### Flow 4: Per-Alert "Why" Explanation & Data Transparency

#### Goal
Demystify every alert trigger so the driver understands exactly which fusion signals (eye closure, gaze angle, phone detection, heart rate) fired the buzzer and phone alarm. Clearly articulate what sensor evidence was processed and what was retained on the phone versus discarded.

#### Trigger
- Tapping the "Why" section on the Live screen during an alert.
- Expanding any alert row in Trip Details (`/trip/[id]`).
- Tapping "Inspect trigger" on an incident item.

#### Screen Wireframe: Expanded Per-Alert "Why" Modal (360dp Wide)

```
+------------------------------------+ 360dp
| [1] Alert Details                  | type: title (28/34 700)
|     Repeated alarm · 14:32:05      | type: caption (13/18 400), textSec
+------------------------------------+
| [2] TRIGGER EVIDENCE               | Section
| +--------------------------------+ | surface: #14171A
| | Eye Closure (Primary)          | | Row
| | Eyes closed for 2.1 s          | | type: body (17/24 400), text
| | Exceeded 1.8 s threshold       | | type: caption (13/18 400), textSec
| |--------------------------------| | separator: #2A2F35
| | Gaze Direction                 | |
| | Center-forward before closure  | |
| |--------------------------------| |
| | Heart Rate (Garmin Watch)      | |
| | 64 bpm · RMSSD fatigue marker  | |
| | Autonomic fatigue confirmed    | |
| +--------------------------------+ |
|                                    |
| [3] DATA & PRIVACY AUDIT           | Section
| +--------------------------------+ | surface: #14171A
| | Stored on this phone           | | Row
| | • Alert timestamp: 14:32:05    | | bullet list: caption (13/18)
| | • Duration: 4.2 s              | | textSecondary
| | • Trigger: Eye closure 2.1 s   | |
| |--------------------------------| |
| | Never stored / Discarded       | | Row
| | • Camera video frames: DELETED | |
| | • Facial biometric coordinates | |
| | • Audio recordings: NONE       | |
| +--------------------------------+ |
|                                    |
| [4] [         CLOSE DETAILS          ] | Button: secondary (48dp)
+------------------------------------+
```

#### Exact Copy Strings (English Only)
- Header: `"Alert Details"`
- Subtitle: `"{pattern} at {time}"`
- Section 1: `"Trigger evidence"`
- Section 2: `"Data & privacy audit"`
- Reasons Plain-Language Mapping:
  - `face drowsy`: `"Drowsy face: long eye closure or drooping eyelids exceeding threshold."`
  - `face distracted`: `"Looking away: gaze diverted from road center for > 1.5 seconds."`
  - `phone sustained`: `"Phone in use: handset detected at ear or texting in lap."`
  - `physio confirms`: `"Heart rate confirms: autonomic nervous system fatigue detected by watch."`
  - `physio elevated`: `"Heart rate shows fatigue: elevated fatigue index or sustained HRV drop."`
  - `test alert`: `"Test alert: manually triggered from phone settings."`
- Data Transparency Audit Copy:
  - Stored: `"Stored on this phone: timestamp, alert duration, trigger reason, and vehicle speed. Encrypted in local SQLite database."`
  - Discarded: `"Discarded immediately: raw camera video frames, facial geometry mesh, and raw physiological waveforms. Never uploaded anywhere."`

#### Accessibility
- **Touch Target**: The expansion row has `minHeight: touch.min` (48dp) and full horizontal touch bounds.
- **TalkBack**: Reads composite summary: `"Alert Details: Repeated alarm. Triggered by eye closure of 2.1 seconds. Heart rate fatigue confirmed. Double tap to close."`
- **Reduce Motion**: Expand/collapse animation switches from height spring to instant layout update when system reduced motion is active.

#### i18n Keys (en.ts additions)
```typescript
'why.title': 'Alert Details',
'why.evidence': 'Trigger evidence',
'why.audit': 'Data & privacy audit',
'why.stored': 'Stored on this phone',
'why.storedDetail': 'Timestamp, alert duration, trigger reasons, and vehicle speed. Stored locally.',
'why.discarded': 'Discarded / Never stored',
'why.discardedDetail': 'Raw camera video frames, facial landmark mesh, and biometric IDs are processed in RAM and discarded.',
'why.map.drowsy': 'Drowsy face: eye closure of {s} s exceeded threshold.',
'why.map.distracted': 'Looking away: gaze diverted from road for {s} s.',
'why.map.phone': 'Phone in use: device held to ear or operated while driving.',
'why.map.physioConfirms': 'Heart rate confirms: autonomic fatigue detected by watch.',
'why.map.physioElevated': 'Heart rate shows fatigue: elevated fatigue index.',
'why.map.test': 'Test alert initiated by driver.',
```

---
