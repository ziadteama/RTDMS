---
title: "Physiology Decision Log — is the HR/HRV fatigue model usable? (Nov 2026)"
tags:
  - subsystem
  - physiology
  - fusion
  - decision-log
aliases:
  - physio decision log
  - HRV model investigation
status: open-decision
code_path: models/physiology
---

# Physiology Decision Log — is the HR/HRV fatigue model usable?

↑ [[Home]] | [[Physiology Subsystem]] | [[Models Index]] · numbers: `models/physiology/docs/MPDDF.md`
· reviews: [[Codex Review 1 - Personalisation]] · [[Codex Review 2 - Whole Case]]

Investigation run 2026-11-20 on branch `physio/mpddf-pilot`. **Start here when you come back.**
Section 8 is the "where we left off" list.

## 1. The problem we started with

The WESAD-trained fatigue artifact (`fatigue_wesad_v1.json`, branch `physio/wesad-fatigue-train`)
scored **LOSO AUROC 0.545 = chance**. Three reasons, none a bug: wrong label (lab *stress*, not
drowsiness), wrong sensor (Empatica E4, not Garmin), tiny data (15 subjects).

## 2. What we did

1. Literature check: wrist-HRV drowsiness detection is weak across people (e.g. ~61 % SVM
   accuracy in a 30-person wrist study); high accuracies (~92 %) are mostly *personal* models, and
   leave-one-person-out drops ~15 points.
2. Picked **MPD-DF** (Sci. Data 2026, 50 drivers, 2 h simulator, physician EEG-based fatigue labels
   0–4, raw ECG, CC BY 4.0). Verified from the paper and figshare, not assumed. Facial video is not
   public; UL-DD was rejected because its Zenodo files are restricted.
3. Built `tools/mpddf_pilot.py`: ECG → R peaks → RR → the **same `RrHrv` code the Pi runs** →
   60 s windows every 5 s → labels → leave-one-subject-out (LOSO) logistic regression / random forest.
   Bug found and fixed on the way: feeding the whole recording before computing left only the last
   120 s (68 windows instead of ~6,300).
4. 5-participant pilot: inconclusive (only 2/5 ever reach label ≥ 2).
5. Full 50-participant run (all ~1.1 GB downloaded, EEG files skipped): 66,454 windows.

## 3. Results in plain words

Target: awake (label 0) vs drowsy (label ≥ 2). 6.3 % of windows are drowsy. 34 of 50 drivers ever
get drowsy, so only they can be scored.

**AUROC** (0.5 = coin flip, 1.0 = perfect), measured inside each held-out driver, averaged:

| What the model sees | AUROC |
|---|---|
| WESAD model (old) | 0.545 (pooled) |
| HRV only (needs RR) | 0.74 |
| **Heart rate only (no RR needed)** | **0.76** |
| HR + HRV | 0.73 |
| **Just the clock (time into the drive)** | **0.84** |
| HR + clock | 0.84 |

**Accuracy / recall / precision** (best model: HR only, vs the driver's own first 5 min):

| Setting | Accuracy | Recall (drowsy caught) | Precision (alerts that were right) | False alarms |
|---|---|---|---|---|
| Sensitive | 70 % | 66 % | 13 % | 30 % of awake windows |
| Medium | 90 % | 15 % | 16 % | 5 % |
| Strict | 94 % | 4 % | 39 % | 0.4 % |

"Never say drowsy" is already 93.7 % accurate, so accuracy is misleading here. No setting is both
useful and trustworthy.

Quick fixes tried, none helped (at 5 % false alarms): 5/15-min HR trends → recall 16 %; + HRV
trends → 15 %; requiring the signal to last ~5 min → 9 % (worse). Clock alone: 31 %.

## 4. Questions answered along the way

- **Is RR our problem? No.** MPD-DF is perfect chest-ECG RR (0 % bad beats) and it is still weak.
  Dropping RR entirely (HR only) loses nothing. Garmin's patchy RR (~50 % empty batches) is a
  *second*, smaller problem that only affects HRV.
- **Can we get HRV from HR? No.** Reported HR is averaged over several beats; beat-to-beat detail
  (RMSSD, pNN50) is gone. "HR wobble" (SD of HR over minutes) is a coarse SDNN stand-in. Call it
  HR variability, never HRV.
- **Did the metrics go up?** Above chance, unlike WESAD, but like-for-like pooled AUROC only
  0.55 → 0.63, precision ~16 %, and the clock beats it. Not good enough to rely on.
- **Can it be personal to each driver?** Yes, three levels:
  1. *Personal baseline*: first 5 min of each drive (tested).
  2. *Personal normal profile*: learned from several normal drives (not testable on MPD-DF, which
     has one drive per person).
  3. *Personal model*: retrained per driver on drowsy episodes (future work).

## 5. Second opinion (Codex), verified

**Review 1** ([[Codex Review 1 - Personalisation]]): adopt with changes. Re-run by Claude, numbers
reproduced exactly:
- Level 1's gain is **not proven**: +0.031 AUROC, 95 % CI −0.027 to +0.094, improved 19/34 drivers,
  Wilcoxon p = 0.44.
- HR beyond the clock: +0.0065 (CI −0.031 to +0.042). Not established.
- 4 drivers (S04, S09, S13, S22) are already fatigued in their 5-min baseline, so level 1 calibrates
  to "tired" for them.
- Level 2: plausible, not demonstrated (resting HR swings ~3 bpm week to week, plus caffeine,
  temperature, sleep).

**Review 2** ([[Codex Review 2 - Whole Case]]): single best recommendation, quoted:
> Make physiology an optional, quality-gated research channel, ship vision-led alerts, and retain
> physiological escalation only if a small paired evaluation demonstrates added value.

Top 3 solutions:
1. **System-level test** (best): physiology reports HR trends + quality; alert changes run in
   *shadow mode*; missing/normal HR may never cancel a clear eye-closure alert. 8–12 volunteers,
   repeated simulator sessions, independent observer labels; compare camera-only vs camera+time vs
   camera+physiology on false alerts/hour at matched sensitivity and detection delay. ~1–2 weeks.
   First step: a one-page protocol, written before collecting data.
2. **Motion-aware quality** (most achievable): use the FR265 accelerometer to know when optical
   data is unreliable (steering, reaching, loose strap) and abstain. ~3–5 days + one 20-min
   chest-strap reference session. Motion is quality only, never a fatigue feature.
3. **Pre-drive readiness** (conditional pivot): sleep questionnaire + reaction-time test + resting
   HR (+ maybe Garmin Stress / Body Battery via `SensorHistory`) to predict how someone will drive.
   Only if a teammate can own it; half-day API check first.

Stop doing: more personalisation/model searching/synthetic RR to rescue the fatigue claim; a
MAX30102 bracelet to fix a weak signal; stress labels or camera outputs as physiological ground
truth; new microsleep/steering/skin-temperature classifiers without real labels. Breathing test:
at most one more day.

## 6. Problems found in the repo (verified, not fixed yet)

| Where | Problem |
|---|---|
| `fusion/src/dms_fusion/__init__.py` (physiology block, ~line 49) | Physiology alone can trigger a beep and escalate alerts; no freshness or quality check |
| `models/physiology/src/dms_physiology/garmin_receiver.py` `_main` (~line 240) | Logs heart data to disk by default — contradicts [[4.3 Ethics]] §4.3.1.1 ("no biometric data stored permanently"). Needs separate consented research logging vs deployment mode |
| `models/physiology/tools/mpddf_pilot.py` `baseline_normalise` | Scores the 5 calibration minutes against themselves → level 1 numbers slightly optimistic |

## 7. Where Claude and Codex agree (current recommendation)

Physiology is **not** a fatigue detector. It is an experimental, quality-gated, per-driver
confirming channel; the camera decides. Report the negative result honestly:

> We built the wearable data path and quality handling, then tested whether heart signals detect
> fatigue. HRV showed a link within each person but almost nothing beyond time spent driving;
> useful alert confirmation is unproven.

## 8. Where we left off — next steps (none started)

1. Fix the fusion stub (physiology can't fire alone; require fresh + good quality; never veto a
   face alert) and the receiver logging default. Branch `fusion/<topic>` / `physio/<topic>`.
2. Write the one-page system-test protocol (Codex solution 1).
3. Motion-aware quality from the watch accelerometer (solution 2).
4. Optional: one day on the breathing features (`tools/mpddf_resp.py` → `data/mpddf_resp.csv`
   extracted, never evaluated).
5. Decide whether drive time enters fusion as its own, honestly-labelled input.

**Still needed from the team:** Garmin `garmin_rr_*.csv` logs from the Pi; a chest strap (e.g.
Polar H10) for one reference session; Pi + watch + camera time for logging; a decision on the
target (default wake vs label ≥ 2).

## 9. Reproduce

Everything is in `models/physiology/docs/MPDDF.md` §8. Data lives in `models/physiology/data/mpddf/`
(gitignored, re-downloadable from figshare `10.6084/m9.figshare.28455737`). Python env:
`~/.venvs/mpddf` (numpy, scipy, scikit-learn, mne, neurokit2, pandas).
