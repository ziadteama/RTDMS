# Flow 9: eye calibration

Part of [Sahi UX redesign](../UX.md). Subsystem note: `Subsystems/Eye Calibration.md`.

#### Goal
Measure how far the driver's eyes close, using the phone's front camera, so the Sahi unit can set its own closed-eye threshold. Takes about a minute; skippable.

#### Entry points
- **Onboarding**: consent, permissions, connect, eye calibration (skippable), emergency contacts.
- **Settings > Unit > Eye calibration**: run or repeat. Next to it, **Driving position** is the existing Pi-camera calibration.
- **Drive**: a hint link while no eye calibration is saved.

#### Screens
1. **Intro**: what happens and that no picture is stored or sent. Start / Skip.
2. **Framing**: live front-camera view with an oval and three ticks (face in oval, enough light, head straight). Continues when all three hold.
3. **Eyes open**: look straight ahead, 10 s, progress bar. The first 2 s are discarded.
4. **Eyes closed**: close eyes gently, 3 s. Voice and haptic cue when to open.
5. **Result**: grade (good / fair / poor), Save, Retry, and a sync line (saved here, sent to your Sahi unit, or waiting for it to connect). A poor result offers Retry only.
6. **Failure states**: too dark, face not found, head turned, eyes not closed enough, too few readings. Each names one fix and offers Retry.

No EAR, ratio or SNR numbers appear in these screens.

#### Rules
- The camera is on only while a calibration screen is shown.
- Demo mode runs the flow on a simulated face and sends nothing.
- Status: not yet verified on the realme GT 6T.
