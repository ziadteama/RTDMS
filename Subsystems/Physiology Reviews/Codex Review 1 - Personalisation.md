---
title: "Codex review 1 — personalisation ladder (2026-11-20)"
tags: [physiology, review, codex]
---

# Codex review 1 — personalisation ladder

↑ [[Physiology Decision Log]]

Read-only review by Codex CLI 0.154.0, 2026-11-20. Brief below the review. Numbers in point 1 and the "4 subjects already fatigued in baseline" claim were **re-run and reproduced exactly** by Claude.

## Review (verbatim)

**Verdict: adopt with changes.** Keep Level 1 as experimental deviation reporting; make Level 2 a hypothesis to test, not the main promised improvement. Defer Level 3. None currently establishes reliable physiological confirmation of drowsiness.

1. **Level 1’s improvement is inconclusive.** I reproduced the pipeline’s balanced logistic LOSO on 50,379 windows, then bootstrapped the **34 paired subject AUROCs**, 20,000 times (seed 42). Raw: **0.6886**; normalised: **0.7192**; difference **+0.0306**, percentile 95% CI **−0.0273 to +0.0943**. Only 19/34 improved; paired Wilcoxon p=0.436. This supports neither proven superiority nor equivalence. These intervals describe subject variation conditional on the fitted LOSO predictions, without retraining each bootstrap. Also, a learned classifier’s performance does **not** validate a simple “below baseline” rule.

2. **Time confounding remains unresolved.** HR+time versus time alone improved **0.8365 → 0.8429**, paired difference **+0.0065**, 95% CI **−0.0306 to +0.0415**. I additionally compared opposite-label windows within each subject’s same five-minute elapsed-time bin: 55 eligible bins across 29 subjects, weighting bins by positive–negative pair count, then averaging subjects equally. HR AUROC was **0.699**, time **0.695**, HR+time **0.703**. Thus HR retains local discrimination, but even local time ordering does; this does not establish independent information. Next test: training-fold-only flexible time splines, with/without HR, plus tighter matching and independent drives. “HR falls during *any* long drive” is not established.

3. **Level 2 is plausible, not demonstrated.** These single-session-per-subject data cannot test cross-drive superiority. A historical profile could detect an already-low starting HR that Level 1 normalises away, but caffeine, temperature, illness, sleep and workload can shift the reference. “Normal drives” still need credible selection; anomaly detection does not identify the anomaly’s cause. [Quer et al.](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0227709) found substantial personal stability alongside typical weekly resting-HR fluctuations around 3 bpm and occasional larger changes—support for personal references, not drowsiness detection. Test a historical reference **alongside** the current-drive offset, using held-out future sessions.

4. **Deferring Level 3 is sensible; the rationale is too absolute.** Face-generated labels create correlated errors and cannot establish independent confirmation. They do not inevitably make physiology copy face: weak supervision can help when assessed against independent outcomes. Effective sample size is independent episodes/drives, not thousands of overlapping windows. Independently adjudicated labels and partial pooling across drivers could reduce personal training requirements.

5. **Prioritise fusion evaluation.** Compare face+time against face+time+physiology on independently labelled, held-out drives; measure false alarms/hour, episode recall and delay, including all-normal drivers. Physiology should provide optional positive support, never veto a strong face warning. The reported 13.9% recall makes mandatory confirmation particularly questionable. Retain ambiguous periods for secondary evaluation rather than assessing only clean extremes.

6. **Concrete adoption changes:** report signed feature deviations, quality and baseline readiness—not a blanket “HR/HRV below baseline” fatigue interpretation. Start scoring after calibration; four subjects’ baseline periods already contain label 1. Pursue HR-first, but current `RrHrv` HR features are RR-derived: Garmin’s separate HR field needs its own validated path. Keep HRV optional and time separate. The documented deployment gates remain unmet.

No files were edited or committed.

## Brief given to Codex (verbatim)

You are reviewing a recommendation for a graduation project (RTDMS, a Raspberry Pi driver monitoring
system). READ-ONLY review: do not edit files, do not commit. You may read files and run read-only
Python analyses on the saved CSVs to check claims. Be a skeptical reviewer; disagree where the
evidence does not support the recommendation.

## Context
- Repo root: current directory. Physiology model: `models/physiology/`. Read
  `models/physiology/docs/MPDDF.md` (plan, results, gates) and `tools/mpddf_pilot.py` (pipeline).
- Live sensor: Garmin FR265 via a Connect IQ app streaming RR intervals over BLE to the Pi
  (`docs/packet_format.md`, `docs/garmin/STEP1_2_RESULTS.md`). ~50% of 1 s batches carry no RR.
- Physiology's role (agreed): a CONFIRMING signal for the face/PERCLOS drowsiness model in fusion,
  never a standalone alarm. Models report, fusion decides.
- Previous model (WESAD stress labels): LOSO AUROC 0.545.

## What was measured (MPD-DF, 50 subjects, 2 h simulated drive, physician EEG fatigue labels 0-4)
Windows: 60 s, every 5 s, features from clean ECG RR via the same `RrHrv` code as the Pi.
Data: `models/physiology/data/mpddf_windows.csv` (columns subject, t_s, label, purity, quality,
7 features). Target wake(0) vs label>=2, label 1 dropped, purity>=0.8. 6.3% positive; 34/50
subjects have both classes. Leave-one-subject-out logistic regression (class_weight balanced).
"Baseline-normalised" = z-score each subject's features vs its own first 5 min of windows.

Per-subject AUROC mean (34 subjects):
- raw 7 features 0.689; baseline-normalised 0.719 (RandomForest 0.530 -> 0.641)
- HR only (mean HR + slope, baseline-norm) 0.759; HRV only 0.738; HR+HRV 0.725
- time-on-task only 0.836; HRV+time 0.842; HR+time 0.843
- pooled AUROC baseline-norm 0.633, raw 0.430
- HR-only at 5% false-alarm rate: recall 13.9%, precision 16.4%
- adding causal 5/15-min trend features or 5-min output smoothing did NOT help (smoothing hurt).

## The recommendation under review
Adopt a personalisation ladder:
- Level 1 (adopt now): per-drive personal baseline = first 5 min of each drive; output
  "HR/HRV deviation below this driver's baseline" to fusion.
- Level 2 (main target): per-driver normal profile learned from several NORMAL drives (no drowsy
  labels needed), stored on the Pi as a few numbers; flag deviations below it.
- Level 3 (future work only): per-driver supervised model trained on face-flagged drowsy episodes
  (rejected for now: needs many drowsy episodes; labels from the face model make physio copy face
  rather than independently confirm it).
Also: drop dependence on RR for the core signal (HR only), keep HRV optional when RR coverage is good;
add time-on-task as a separate fusion input.

## Questions — answer each directly, with evidence or a quick check where possible
1. Is Level 1 actually better than the population model, or is the +0.03 within noise? (A
   per-subject paired comparison or bootstrap over subjects on the CSV would settle it.)
2. Is the baseline-normalised HR signal just a proxy for time-on-task (HR drifts down over any
   long drive)? Suggest or run a test that separates them (e.g. time-matched comparison, or
   residualising on time).
3. Is Level 2 likely to beat Level 1, and what are its risks (day-to-day HR variation, caffeine,
   temperature, starting a drive already tired)? Anything in the literature you know of?
4. Is the reasoning against Level 3 sound?
5. Is there a better option we missed (e.g. a completely different use of physiology in fusion,
   different target, different evaluation)?
6. Your final verdict: adopt the ladder as stated, adopt with changes (say which), or reject.

Keep the answer under ~600 words. Lead with the verdict. Report any numbers you computed and how.
Python with pandas/sklearn: /home/teamacs/.venvs/mpddf/bin/python (run from models/physiology).
