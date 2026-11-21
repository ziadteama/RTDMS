# Flow 5: SOS

Part of [Sahi UX redesign](../UX.md).

### Flow 5: Emergency SOS & Two-Stage Escalation

#### Countdown Length Decision Rationale
- **Benchmarking**:
  - *Pixel Watch / Apple Watch*: 60-second countdown before automated dispatch.
  - *Current Sahi Implementation*: 30 seconds (`COUNTDOWN_S.crash = 30`).
  - *Egyptian Emergency Services Context*: Egyptian ambulance authority (123) reports ~90% of incoming automated or panic calls are false alarms or unverified. Auto-dispatching emergency vehicles after minor road bumps or dropped phones creates massive institutional strain and risks driver legal liability.
- **Trade-off Analysis**:
  - *30 seconds*: Dangerously short. A driver dazed by an airbag deployment or struggling with a detached phone mount cannot locate and tap "I'm OK" within 30 seconds, causing premature dispatches.
  - *60 seconds*: Excessive delay for true severe impacts where drivers are unconscious and experiencing arterial bleeding or airway compromise.
- **RECORDED DECISION**:
  - **Default Countdown**: **45 seconds**.
  - **User Configuration**: User-configurable in `Settings -> Emergency` with choices: **30 s / 45 s / 60 s**.
  - **Acoustic & Haptic Warning from Second 0**: From the instant of crash detection ($t = 0$), the phone rings an assertive alarm tone, speaks aloud via TTS (*"Crash detected. Sending help in 45 seconds. Tap I'm OK to cancel."*), and initiates haptic pulses (Medium impacts 45–11s, Heavy continuous impacts last 10s).
  - **Two-Stage Architecture**:
    - **Stage 1 (45 s)**: Contacts-first. Upon countdown expiration, parallel dispatch begins:
      - **WhatsApp Relay**: Automated notification via Sahi WhatsApp service with map link.
      - **Link-Free SMS**: Link-free SMS containing 5-decimal coordinates (`Location (paste in Maps): {lat},{lon}`) and timestamp dispatched to registered emergency contacts (ASCII-only GSM-7 to bypass carrier spam filters).
    - **Stage 2 (15 s Staging Window)**: "Calling 123 in 15 s" screen. Auto-dialing proceeds **only if the phone remained completely motionless** (confirming driver incapacity). If physical movement or screen touch is detected, auto-dialing pauses and converts to an explicit "Tap to Call" prompt.
  - **Configurable Emergency Number**: Defaults to 123 (Ambulance in Egypt), with settings option for 112 (Unified Emergency) or a custom number.
  - **Onboarding Consent**: Explicit consent check required during onboarding before auto-calling permissions are granted.

#### Screen Wireframe: Stage 1 SOS Countdown (360dp Wide)

```
+------------------------------------+ 360dp
| [1] Crash detected                 | bg: alert.max (#FF2E3A)
|     Help will be dispatched        | type: title (28/34 700), onAlert.max
+------------------------------------+
| [2] COUNTDOWN TIMER                |
|                                    |
|          Sending help in           | type: headline (20/26 600)
|                                    |
|                 45                 | type: countdown (120/132 800)
|                                    | tabular numbers
| [================================] | ProgressBar: height 10dp
|                                    | onAlert.max (#FFFFFF)
+------------------------------------+
| [3] [      [!] FALSE ALARM       ] | FeedbackChip: touch.min (48dp)
|                                    | bg: surfaceRaised (#1C2024)
| [4] [                            ] |
|     [          I'M OK            ] | Button: primary, action
|     [                            ] | touch.huge (96dp) minHeight
|                                    |
| [5] [          SEND NOW          ] | Button: ghost (48dp)
+------------------------------------+
```

#### Screen Wireframe: Stage 2 Emergency Call Staging (360dp Wide)

```
+------------------------------------+ 360dp
| [1] SMS Dispatched                 | bg: background (#0B0D0F)
|     Coordinates sent to 2 contacts | type: headline (20/26 600), text
+------------------------------------+
| [2] EMERGENCY CALL STAGING         |
| +--------------------------------+ | surface: #14171A
| | Calling Ambulance (123) in:    | | type: headline (20/26 600)
| |                                | |
| |               15               | | type: state (44/52 800), alert.max
| |                                | |
| | Motion check: Phone is still   | | caption: (13/18 400), textSec
| | Untouched: Auto-dialing armed  | |
| +--------------------------------+ |
|                                    |
| [3] [      CANCEL CALL (123)     ] | Button: destructive
|                                    | touch.large (64dp) minHeight
|                                    |
| [4] [          CALL NOW          ] | Button: secondary (48dp)
+------------------------------------+
```

#### Exact Copy Strings (English Only)
- Stage 1 Countdown:
  - Header: `"Crash detected"`
  - Subheader: `"Sending help in"`
  - Cancel Button: `"I'm OK"`
  - False Alarm Chip: `"[!] False alarm"`
  - Accelerate Button: `"Send now"`
  - Spoken Voice Prompt: `"Crash detected. Sending help in {s} seconds. Tap I am OK to cancel."`
- Stage 2 Call Staging:
  - SMS Header: `"Emergency SMS dispatched"`
  - Call Staging: `"Calling {number} in {s} seconds"`
  - Motion Notice Still: `"Phone is motionless. Auto-dialing emergency dispatch."`
  - Motion Notice Moved: `"Phone movement detected. Auto-dial paused. Tap Call Now if you need help."`
  - Cancel Call: `"Cancel call ({number})"`
  - Call Immediately: `"Call now"`
- Emergency Completed:
  - Header: `"Help requested"`
  - Status Line SMS: `"SMS sent to 1 contact"` / `"SMS sent to {n} contacts"` (no URL in SMS; 5-decimal coordinates)
  - Status Line Call: `"Starting call to {number}…"` -> `"Calling {number}"` / `"Could not start the call"`
  - Per-Contact Channel Status: WhatsApp (`waiting` / `sent` / `delivered` / `read` / `failed` / `no data`), SMS (`sent` / `delivered` / `failed`)
  - Close: `"Close"`

#### Motion & Touch Gating Mechanics
- During Stage 2 ($15 \text{ s}$ buffer):
  - Phone monitors `SensorManager` accelerometer variance ($\sigma^2_a$).
  - If $\sigma^2_a > 0.15 \text{ g}$ (indicating the driver picked up the phone or moved), or if any screen touch occurs outside the Cancel button:
    - Auto-dial timer freezes.
    - Status changes to `"Motion detected. Auto-dial suspended."`
    - A prominent `"Call Now"` button remains enabled if help is actually needed.

#### Accessibility
- **Touch Targets**:
  - Stage 1 `"I'm OK"` button uses `touch.huge` (**96dp minHeight**). It covers the full primary reachable area of the screen.
  - Stage 2 `"Cancel Call"` button uses `touch.large` (**64dp minHeight**).
  - All secondary chips and buttons maintain $\ge 48\text{dp}$.
- **TalkBack**: Assertive live region for countdown: updates announced at $45\text{s}$, $30\text{s}$, $15\text{s}$, and every second below $10\text{s}$.
- **Reduce Motion**: The progress bar updates tick-by-tick (1s discrete steps) instead of continuous linear width interpolation. Haptics remain active as they convey vital status to a disoriented driver.

#### i18n Keys (en.ts additions)
```typescript
'sos.stage1.title': 'Crash detected',
'sos.stage1.sendingIn': 'Sending help in',
'sos.stage1.imOk': "I'm OK",
'sos.stage1.falseAlarm': 'False alarm',
'sos.stage1.sendNow': 'Send now',
'sos.stage2.smsSent': 'Emergency SMS dispatched',
'sos.stage2.callingIn': 'Calling {number} in {s} seconds',
'sos.stage2.motionStill': 'Phone is motionless. Auto-dialing emergency dispatch.',
'sos.stage2.motionDetected': 'Phone movement detected. Auto-dial paused.',
'sos.stage2.cancelCall': 'Cancel call ({number})',
'sos.stage2.callNow': 'Call now',
'sos.settings.duration': 'SOS countdown length',
'sos.settings.duration30': '30 seconds',
'sos.settings.duration45': '45 seconds (Recommended)',
'sos.settings.duration60': '60 seconds',
'sos.settings.number': 'Emergency dispatch number',
'sos.settings.consentAutoCall': 'Allow automatic emergency calling after crash',
```

---
