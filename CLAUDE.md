# RTDMS — Real-Time Driver Monitoring System

B.Sc. Final Year Project, Arab Academy for Science, Technology and Maritime Transport,
College of Engineering and Technology, Computer Engineering Department. Report dated May 2026
(Project 1 complete; this repo starts Project 2 — the implementation phase).

Team: Omar Khalifa, Youssef Medhat, Ziad Hesham/Teama, Malek Ahmed, Omar Deyaa.
Supervisor: Dr. Emad Elsamahy.

Full parsed source report: `.firecrawl/DMS_FINAL_REPORT.md` (gitignored, regenerate from
`C:\Users\ziadt\Desktop\GradProject\DMS_FINAL_REPORT.docx` via `firecrawl parse` if missing).
Other related docs live in `C:\Users\ziadt\Desktop\GradProject\` (business model, SWOT, literature
survey, dataset selection/collection, user stories & requirements, stakeholders & use-cases, etc.)
— not yet pulled into this repo.

## What it is

A vision + physiological driver monitoring system detecting drowsiness, gaze deviation/distraction,
and phone usage in real time, with heart-rate/HRV as a confirming physiological signal, escalating
to buzzer + vibration alerts. Designed for integration into a V2C Smart Dash Camera. Positioned as
B2B: OEMs, commercial fleets, logistics, public transport operators.

## Problem it addresses

~1.19–1.3M global road deaths/year; drowsiness implicated in 3–30% of crashes; in Egypt, 5,260 killed
/ 76,362 injured in 2024 road accidents (CAPMAS), ~64% attributed to human factors. Sleepy drivers'
HR drops ~9%. Phone distraction takes eyes off road long enough to travel significant distance
unaware at highway speed.

## Objectives (SMART, from Project 1)

- Eye closure / PERCLOS via camera on Raspberry Pi: <1s latency, ≥85–90% accuracy, alert if eyes
  closed beyond 2–3s threshold.
- Gaze/head pose tracking: flag off-road gaze >2s, ≥85–90% accuracy, buzzer on threshold breach.
- Phone-usage detection (AI image classification): ≥85–90% accuracy, alert within 1s.
- Heart rate / HRV (wearable, MAX30102): stable BPM acquisition, sustained-trend detection,
  confirms/escalates vision-triggered alerts.
- End-to-end alert latency target: <500ms overall system, <100ms Pi↔wearable Bluetooth trigger delay.

## System architecture

Raspberry Pi–centered. Two sensing subsystems feed an AI decision-fusion stage that drives alerts:

1. **Behavioural (vision) subsystem** — camera → calibration (position/posture/lighting) →
   preprocessing (resize, normalize, stabilize, denoise) → feature extraction (facial landmarks, eye
   state/closure duration, gaze direction, head pose, phone presence) → AI models (drowsiness,
   attention, distraction/object detection).
2. **Physiological subsystem** — wearable HR sensor → signal conditioning/preprocessing → features
   (HR level, spikes, deviation from baseline, HRV) → stress/fatigue model.
3. **AI processing & decision fusion** — combines behavioural + physiological model outputs to
   reduce false alarms vs. single-source systems; produces a risk level.
4. **Alert generation** — buzzer + vibration, severity-graded:
   - Normal → no buzzer
   - Short distraction / mild gaze deviation → short intermittent beep
   - Long eye closure / repeated drowsiness → repeated buzzer + vibration
   - Phone usage / severe distraction → continuous buzzer
   - Combined behavioural+physiological risk → maximum alert + strong vibration

Non-functional: <500ms end-to-end latency; ≥85% vision accuracy across lighting; operating range
−10°C to 50°C; low power; privacy-first — local/edge processing only, no cloud, no persistent
biometric storage; secure local interfaces (I2C, CSI) rather than networked comms.

## Selected hardware (final BOM)

| Component | Choice | Est. price |
|---|---|---|
| Edge compute | Raspberry Pi 5 (8GB) | 13,000 EGP |
| AI accelerator | Raspberry Pi AI HAT+ 26 TOPS (Hailo-8) | 8,750 EGP |
| Camera | Pi IR camera 5MP 160° | 1,050 EGP |
| Wearable sensor | MAX30102 (PPG, HR/SpO2, I2C) wristband | 95–520 EGP |
| **Total** | | **~22,895–23,320 EGP** |

Alerting: buzzer + vibration motor, timestamped local event log, optional dashboard.

## Software stack

Python, OpenCV, MediaPipe Face Mesh (EAR/PERCLOS, gaze, head pose — fast + accurate per literature),
YOLOv5 (phone/object detection), Random Forest / SVM for HR/HRV fatigue classification, CVAT/Roboflow
for annotation.

## Datasets (Project 1 selection)

| Dataset | Use |
|---|---|
| UTA-RLDD | Drowsiness/PERCLOS training (60 subjects, real-life progressive drowsiness) |
| AUC Distracted Driver | Phone-use & distraction classification (normal + 9 classes) |
| MRL Eye Dataset | Eye closure/PERCLOS (84,898 images, incl. IR) |
| DG-Unicamp | Gaze tracking / head pose (gaze-zone annotations) |
| WESAD | Physiological fatigue/stress support (15 subjects: neutral/stress/amusement) |

Also reviewed but not selected as primary: CEW, Drive&Act, NDS.

Custom data-collection plan: 10–20 volunteer drivers, varied age/gender/eyewear, Pi Camera Module v3
or IR module at 1920×1080/30fps mounted beside the right door; consent-based; labeled with
CVAT/LabelImg/Roboflow; augmentation via rotation/blur/noise/contrast variation.

## Ethics

Local/edge-only processing of video, landmarks, gaze, HR — nothing stored persistently or sent over
Wi-Fi/Bluetooth to the cloud. Secure local interfaces only. Consent + transparency + ability to
disable monitoring. Fairness: must be evaluated across age/gender/skin tone to avoid biased accuracy.
Alert tuning must avoid false-alarm fatigue. Framed as a driver-assistance tool, not autonomous
safety — driver retains responsibility. Requires continuous post-deployment validation.

## Business framing (SWOT/PESTLE highlights)

- **Strengths**: multimodal (behavioural+physiological) reduces false positives vs. single-sensor;
  real-time; personalizable to baseline HR.
- **Weaknesses**: HR sensor motion/contact sensitivity; camera lighting sensitivity; compute demands;
  possible false alarms.
- **Opportunities**: rising regulatory push for ADAS/safety systems, fleet cost-reduction demand.
- **Threats**: incumbent automotive safety vendors, privacy regulation, hardware cost, driver
  resistance to monitoring.
- Go-to-market: B2B — OEMs, fleets, logistics, public transport (not aftermarket-first).

Commercial benchmark set: Smart Eye AIS, Seeing Machines Guardian Gen 3, Cipia Fleet Sense, Jungo
VuDrive, oToBrite Vision-AI DMS, Valeo DMS, Netradyne Driver-i, Motive AI Dashcam — none publish
pricing; used as functional/feature benchmarks only (full comparison matrix in the source report,
§4.2.2).

## Feasibility & top risks (§4.4)

Face obstruction (sunglasses/masks), false alarms, missed detection, HR sensor noise, real-time
processing delay, hardware headroom, driver-alert fatigue, integration complexity, privacy — all
rated with mitigations in the report; overall assessed as feasible with staged validation.

## Phase Two plan (this repo's actual scope)

1. **Hardware assembly & integration** — Pi 5 + AI HAT+ 26 TOPS; camera mounted cabin-right; wearable
   bracelet w/ MAX30102; Bluetooth link target <100ms trigger delay.
2. **Model training & edge optimization** — MediaPipe Face Mesh (EAR), YOLOv5 (phone detection),
   Random Forest/SVM (HR/HRV fatigue classification); target <500ms end-to-end latency.
3. **Custom data collection & annotation** — 10–20 drivers, CVAT/Roboflow labeling, augmentation.
4. **Sensor fusion & alert logic** — HR/HRV cross-verifies vision cues; buzzer/voice alert within 1s;
   emergency escalation protocol (GPS-based nearest-hospital contact on prolonged unresponsiveness —
   new in Phase 2, beyond Project 1's original scope).
5. **Validation & final prototype testing** — accuracy benchmarking vs. 85–90% targets, environmental
   stress testing (−10°C to 50°C, day/night), final self-contained offline privacy-preserving unit.

## Repo skills available

Copied from `Z:\Plegmo\.agents\skills\` into `.claude/skills/`:
- `obsidian-bases`, `obsidian-cli`, `obsidian-markdown` — Obsidian vault/notes tooling
- `faithful-brief` — lossless delegation-brief writing/verification against source plans
- `find-skills` — discover/install more skills via the Skills CLI
- `ponytail` — minimal/YAGNI-biased coding discipline (default "full" intensity)
