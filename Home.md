---
title: RTDMS Vault Home
tags:
  - home
  - moc
cssclasses:
  - home
---

# RTDMS — Real-Time Driver Monitoring System

B.Sc. Final Year Project, AASTMT Computer Engineering. Full coverage of `DMS_FINAL_REPORT.docx`
(May 2026, Project 1) transcribed section-by-section into this vault, plus the working notes for
Project 2 (the build phase this repo is for).

> [!abstract] Elevator pitch
> A Raspberry Pi–based driver monitoring system that detects drowsiness, gaze deviation, and phone
> usage from a cabin camera, cross-verified against heart-rate/HRV from a wearable, escalating
> through buzzer + vibration alerts — all processed locally, no cloud.

## Implementation (Project 2)

- [[Open Items and Next Steps]] — **what is not done yet** (hardware, app, SOS, product questions)
- [[MVP Readiness]] — is what we have enough for an MVP? (22 Nov: phone-side yes, full chain no; the gaps and the order to close them)
- [[Project Log 2026-11]] — decisions, evidence and lessons of 21–22 Nov 2026
- [[Demo Prep 2026-11-23]] — live demo dashboard, distraction/calibration fixes from recorded Pi sessions, report audit (23 Nov evening)
- [[Orchestration Playbook]] · [[Dev Environment and Test Devices]] · [[Coordination Board 2026-11]] — how the agents work, how to run and test everything, the raw trail
- [[Agent Guide]] — **start here if you're an agent about to dev, explore, or delegate work**
- [[Models Index]] — status of all models + fusion/alert/firmware
  - [[Physiology Subsystem]] — HR/PRV fatigue inference · `models/physiology/` · **implemented**
    - [[Physiology Decision Log]] — Nov 2026: is the HR/HRV fatigue model usable? MPD-DF results, Codex reviews, next steps
    - [[Physiology New Approach]] — **current plan (23 Nov)**: HR from the Garmin, vital signs + shadow score, watch–Pi–phone sync
    - [[Physiology Fusion Approach]] — superseded: Garmin confirm role + training tiers for fusion
  - [[Face Subsystem]] — EAR/PERCLOS/gaze/head-pose · `models/face/` · **implemented (core)** · live on the Pi via LiteRT, 2026-10-10 ([[Face Subsystem#Running on the Pi|status]])
  - [[Phone Subsystem]] — phone/eating distraction · `models/phone/` · **ONNX wired**
- [[Mobile App End-User Scope]] — Sahi is an end-user product (not admin): audience, needs, audit, target tabs, open product questions · **decided**
- [[Mobile App]] — **Sahi**, the React Native driver app (live view, alerts, crash detection, incident clip) · `app/` · **MVP built** (mock Pi + demo mode; not yet on a phone, Pi endpoints pending)
- [[Raspberry Pi 5 Target]] — the deployment device, surveyed live over SSH
- [[Pi Setup Plan]] — researched optimal configuration + the blockers to resolve first
- [[Competitor App Study]] — dashcam, fleet/driver-monitoring and crash-detection apps studied for Sahi: patterns to copy, mistakes to avoid, gaps · **research (web only, no hands-on teardown yet)**
- [[WhatsApp SOS Relay]] — crash SOS over WhatsApp (unofficial lib) + link-free SMS backup · `relay/` · **verified end to end with real messages**
- [[Pi Runtime]] — the Pi-side runtime (`pi/`): fusion loop, buzzer, BLE phone service, incidents, hotspot · **built, Docker-verified only, not run on the Pi**
- [[Phone-Pi Link]] — Sahi app ↔ Pi transport: research, dashcam reference pattern, recommended BLE + Wi-Fi hybrid, bench-spike plan · **proposed, nothing measured**

> [!warning] Working principle
> The report is a **starting point, not a spec**. Prefer the better/optimal technical option, then
> record the divergence so the final report can be updated or the choice defended.

## Report — full coverage (chapter order)

- [[00 Front Matter]] — declaration, acknowledgment, abstract, acronyms, standards
- [[01 Introduction]]
  - [[1.1 Motivation]]
  - [[1.2 Problem Statement]]
  - [[1.3 Objective]]
- [[02 Literature Survey]]
  - [[2.1 Literature Survey]]
  - [[2.2 Research Gap]]
- [[03 Methodology]]
  - [[3.1 System Architecture]]
  - [[3.2 Technical Description]]
  - [[3.3 Dataset Selection and Collection]]
  - [[3.4 Software Hardware Requirements]]
- [[04 Experiment and Results]]
  - [[4.1 Business Model]]
  - [[4.2 Commercial Market Survey]]
  - [[4.3 Ethics]]
  - [[4.4 Feasibility and Risk Analysis]]
  - [[4.5 Cost Calculation and BOM]]
- [[05 Conclusion]]
  - [[5.1 What Has Been Done in Project 1]]
  - [[5.2 Phase Two Plan]] ← **we are here**
- [[References]]

## Quick jumps

- Hardware/BOM: [[4.5 Cost Calculation and BOM]], [[3.4 Software Hardware Requirements]]
- Datasets: [[3.3 Dataset Selection and Collection]]
- Architecture: [[3.1 System Architecture]]
- Risks: [[4.4 Feasibility and Risk Analysis]]
- What's next: [[5.2 Phase Two Plan]]

## Vault database

![[bases/Report Sections.base]]

![[bases/Subsystems.base]]

## Other project docs (not yet imported)

Still living in `C:\Users\ziadt\Desktop\GradProject\`, not yet pulled into this vault: Business
Model V4.1, Aspect Rationale Report, SWOT Report V3.0, Strategic Analysis V1.0, Data Collection
Final, Dataset Selection Final, Literature survey (standalone), Modified market survey,
Stakeholders & use-case scenarios (PDF), User stories and Requirements (PDF), commercial DMS
hardware market survey report, Motivation.docx, Problem Statement.docx, Proposed System
Concept.docx, SMART objectives.docx, Draft1.pptx / ziads.pptx. Ask to import any of these.

## Repo skills

`.claude/skills/` — `obsidian-bases`, `obsidian-cli`, `obsidian-markdown`, `faithful-brief`,
`find-skills`, `ponytail` (see project [[../CLAUDE.md|CLAUDE.md]] for details).
