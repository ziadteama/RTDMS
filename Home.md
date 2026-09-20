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

- [[Agent Guide]] — **start here if you're an agent about to dev, explore, or delegate work**
- [[Models Index]] — status of all models + fusion/alert/firmware
  - [[Physiology Subsystem]] — HR/PRV fatigue inference · `models/physiology/` · **implemented**
  - [[Face Subsystem]] — EAR/PERCLOS/gaze/head-pose · `models/face/` · **implemented (core)**
- [[Raspberry Pi 5 Target]] — the deployment device, surveyed live over SSH
- [[Pi Setup Plan]] — researched optimal configuration + the blockers to resolve first

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
