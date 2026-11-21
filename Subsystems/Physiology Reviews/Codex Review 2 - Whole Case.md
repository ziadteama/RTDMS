---
title: "Codex review 2 — whole-case solutions (2026-11-20)"
tags: [physiology, review, codex]
---

# Codex review 2 — whole-case solutions

↑ [[Physiology Decision Log]]

Read-only review by Codex CLI 0.154.0, 2026-11-20. The three repo contradictions it cites were **checked by Claude and are real** (fusion stub line ~49, receiver logging default, pilot baseline leak).

## Review (verbatim)

**Make physiology an optional, quality-gated research channel, ship vision-led alerts, and retain physiological escalation only if a small paired evaluation demonstrates added value.**

1. **Best: change the fusion claim and test incremental benefit directly.**

   Physiology should initially report HR trends, quality, and availability while proposed alert changes run in shadow mode. Missing or normal HR must never cancel a clear prolonged-eye-closure alert; physiological escalation remains experimental.

   **Why:** Weak standalone discrimination does not exclude complementary information specifically among ambiguous vision events. But 16% precision at your reported operating point is insufficient evidence for “confirmation.” MPD-DF lacks public facial video, so it cannot establish fusion benefit ([MPDDF.md](/home/teamacs/RTDMS/models/physiology/docs/MPDDF.md)).

   **Needs:** Approximately 1–2 weeks, existing Pi/watch/camera, 8–12 volunteers with repeated simulator sessions. Record synchronized outputs, independent observer event labels, periodic sleepiness ratings, and simulator performance where available. Compare vision-only, vision+time, and vision+physiology with identical temporal filtering; freeze thresholds before testing held-out participants.

   Report false alerts/hour **at matched event sensitivity**, detection delay, abstention coverage, and participant-level uncertainty. Include all-alert sessions and all-normal sessions. Acted closures test integration, not physiological fatigue.

   **Risk:** Too few genuine events; inconclusive benefit is an acceptable outcome. Escalation alone cannot substantiate fewer false alarms.

   **First step:** Write a one-page evaluation protocol defining the events, comparator policies, and deployment gate.

2. **Most achievable wearable contribution: motion-aware availability and graceful degradation.**

   Use wrist acceleration to identify conditions under which optical measurements become unreliable. Evaluate whether the system correctly abstains during steering, loose contact, and disconnection. This is a measurable engineering contribution, although it revises the physiological differentiator.

   **Why:** Garmin supports accelerometer acquisition alongside beat intervals through its [sensor API](https://developer.garmin.com/connect-iq/articles/core-topics/Sensors.html). Your existing evidence establishes resting transport feasibility, not accuracy during driving.

   **Needs:** Roughly 3–5 engineering days, a packet extension or separate message, and preferably a borrowed ECG/chest-strap reference. Run repeated rest, steering, reaching, and contact-loss trials. Report reference agreement alongside retained coverage; measure concurrent Pi cost and watch battery use.

   **Risk:** Wrist movement is not steering-wheel angle or impairment. A motion gate can discard useful data; without a reference, you can establish availability but not measurement accuracy.

   **First step:** Run a 20-minute paired reference session before implementing elaborate filtering. Keep motion as quality information, not a fatigue shortcut.

3. **Conditional research pivot: pre-drive readiness, not immediate fatigue confirmation.**

   Explore whether a brief pre-drive assessment predicts subsequent simulator performance. Candidate inputs: self-reported sleep/sleepiness, a short reaction-time task, resting HR, and optionally Garmin stress/Body Battery.

   **Why:** This matches slow physiological context better than seconds-long microsleep detection. Garmin exposes stress and Body Battery history through [SensorHistory](https://developer.garmin.com/connect-iq/api-docs/Toybox/SensorHistory.html), although device availability, freshness, and offline access need testing. These scores are candidate predictors—not impairment labels.

   **Needs:** At least 2–3 weeks, repeated sessions per participant, and prospective outcomes. Test whether wearable variables improve over the questionnaire/reaction-time baseline.

   **Risk:** Small samples, proprietary algorithms, and substantial scope expansion. Historical wearable data also requires clarifying your privacy boundary. Never output “safe to drive.”

   **First step:** Time-box an on-watch API/freshness check to half a day. Pursue only if another teammate can own it without delaying fusion.

**Explicitly stop doing**

- Further personalization, model-family searches, and synthetic RR degradation as attempts to rescue the current fatigue claim.
- Treating stress labels, acted sleepiness, or camera predictions as independent physiological ground truth.
- Building another MAX30102 bracelet to solve weak label discrimination.
- Launching microsleep, steering-microcorrection, or skin-temperature classifiers without suitable measurements and labels. A generic temperature API does not establish skin-temperature sensing.
- Give the existing breathing experiment at most one exploratory day: respiration versus HR/time, subject-held-out. Chest-respiration success would still require a deployable sensor; it would not validate Garmin-derived breathing.

**Report and defense**

Say: “We implemented wearable acquisition and quality handling, then tested physiological fatigue discrimination. HRV showed within-subject association but negligible improvement beyond elapsed time; useful alert confirmation remains unproven.”

Present the negative result, controls, uncertainty, sensor-domain gap, and revised design as engineering judgment. Describe wearable integration as a differentiating architecture, not demonstrated superiority over commercial systems.

**Repo contradictions worth addressing**

- [Fusion code](/home/teamacs/RTDMS/fusion/src/dms_fusion/__init__.py:49) already permits physiology-only beeps and escalation of phone alerts, without checking freshness or quality.
- [Pilot normalization](/home/teamacs/RTDMS/models/physiology/tools/mpddf_pilot.py:128) also scores baseline windows using their completed baseline: exclude calibration-period predictions from prospective evaluation.
- [Receiver](/home/teamacs/RTDMS/models/physiology/src/dms_physiology/garmin_receiver.py:240) persistently logs biometrics by default, conflicting with [ethics claims](</home/teamacs/RTDMS/Report/04 Experiment and Results/4.3 Ethics.md:21>). Separate consented research logging from deployment.
- [Subsystem documentation](</home/teamacs/RTDMS/Subsystems/Physiology Subsystem.md>) correctly distinguishes wrist PRV from ECG HRV; preserve that distinction in the defense.

## Brief given to Codex (verbatim)

You are a senior advisor on a graduation project. READ-ONLY: do not edit files or commit. You may
read the repo and run read-only analyses. Python with pandas/sklearn/mne/neurokit2:
/home/teamacs/.venvs/mpddf/bin/python (run from models/physiology). Think broadly and creatively,
but be concrete and honest about what is feasible.

## The project
RTDMS: a Raspberry Pi 5 driver monitoring system (B.Sc. graduation project, team of 5). Camera
models already work on the Pi: face (eye closure/PERCLOS, gaze, head pose; `models/face/`) and
distraction (phone call, texting, drinking; `models/distraction/`). A fusion stage (`fusion/`, a
stub) owns alert decisions. The project's pitch (report, `Report/`, CLAUDE.md) is that a
PHYSIOLOGICAL channel (heart rate / HRV from a wrist wearable) confirms and escalates vision alerts
and reduces false alarms — it is the claimed differentiator vs 8 commercial systems, none of which use
a wearable. Constraints: edge-only, privacy-first (no cloud, no persistent biometric storage),
low Pi CPU budget, models report scores + quality and fusion decides.

## The wearable we actually have
Garmin Forerunner 265. Built-in HR broadcast has no RR intervals. A custom Connect IQ app
(`models/physiology/garmin/rr_stream`) streams RR over BLE to the Pi (`docs/packet_format.md`).
Measured at rest: ~50% of 1 s batches carry no RR; window coverage 0.3–0.9
(`docs/garmin/STEP1_2_RESULTS.md`). No chest-strap reference yet; wrist motion while steering is
unmeasured. The originally planned MAX30102 + ESP32 bracelet also has a pipeline in the repo.

## Everything tried so far (details: `models/physiology/docs/MPDDF.md`)
1. WESAD (lab stress labels, E4 wrist): LOSO AUROC 0.545 = chance.
2. MPD-DF (50 drivers, 2 h simulator, physician EEG-based fatigue labels, clean chest ECG):
   leave-one-subject-out, per-subject AUROC mean: HRV 0.72–0.74, HR only 0.76, time-on-task only
   0.84, HR+time 0.84. At 5% false alarms HR recall 14%, precision 16%. Personal 5-min baseline
   normalisation +0.03 (95% CI −0.03..+0.09, not significant). Trend features and smoothing did
   not help. RR quality is NOT the bottleneck (clean ECG still weak). 4 subjects are already
   fatigued during the baseline period.
3. A breathing-rate test (from MPD-DF chest respiration) was started but not evaluated.

## The question
Forget the specific personalisation ladder. Looking at the WHOLE case — the product pitch, the
hardware, the data, the remaining time of a graduation project, and the evidence above — what
solutions do you see? For example (don't limit yourself to these): a different role for
physiology in fusion; different physiological signals the Garmin/bracelet can give (wrist motion /
steering micro-movements from the accelerometer, breathing, skin temperature, Garmin's own stress
or Body Battery); different targets (e.g. predicting impairment risk before a drive, or detecting
microsleep-adjacent events rather than graded fatigue); different evaluation that would show value
honestly; different data (own collection protocol); or changing the claim in the report.

Answer:
1. Your top 3 solutions, ranked, each with: what it is, why it could work (evidence or reasoning),
   what it needs (hardware, data, time), the risk, and the first concrete step.
2. What you would explicitly stop doing.
3. How the team should present the physiology result in the final report and defense.
4. Anything in the repo that contradicts or weakens the current approach (cite files).

Under ~800 words. Lead with your single best recommendation in one sentence.
