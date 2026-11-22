# Flow 9: eye calibration

Part of [Sahi UX redesign](../UX.md). Subsystem note: `Subsystems/Eye Calibration.md`.

#### Goal
Measure how far the driver's eyes close, using the phone's front camera, so the Sahi unit can set its own closed-eye threshold. Takes about a minute; skippable.

#### Entry points
- **Onboarding**: consent, permissions, connect, eye calibration (skippable with Later), emergency contacts.
- **Settings > Unit > Eye calibration**: run or repeat; the row shows the last grade (Good / Fair / Poor) or "not done". Next to it, **Driving position** is the existing Pi-camera calibration (needs the unit online).
- **Drive**: the driver-state detail line ("calibrate") links here when no eye calibration is saved or the Pi reports itself uncalibrated.

#### Screens
1. **Intro**: "Eye calibration", takes about 20 seconds, park first and hold the phone at eye level or in its mount. Start / Later.
2. **Framing**: "Fit your face in the oval", front-camera view with an oval and three ticks (Face in the oval, Good lighting, Looking straight ahead). "Hold still..." then it continues automatically once stable. Cancel returns to the intro.
3. **Eyes open**: "Look at the road, eyes open", 10 s countdown. The first 2 s are discarded. Spoken cue and haptic at the start.
4. **Eyes closed**: "Close your eyes", 3 s countdown, "until you hear the chime". Spoken cue and haptic at the start; spoken "Open." and a success haptic at the end.
5. **Result**: Good / Fair / Poor calibration with a one-line explanation, and a sync line ("Saved to your Sahi unit" or "Will be sent when your unit connects"). Good and Fair: Save, Retry. Poor: Retry, Save anyway. After saving: Done.
6. **Failure**: No face found, Too dark, Head turned, Eyes did not close, Not enough data. Each has one sentence of advice, Retry and Cancel.

No EAR, ratio or SNR numbers appear in these screens.

#### Rules
- The camera is on only while a calibration screen is shown.
- Demo mode runs the flow on a simulated face and sends nothing.
- Status: not yet verified on the realme GT 6T.
