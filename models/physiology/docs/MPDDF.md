# MPD-DF → Garmin fatigue model: plan, steps, and what is needed

Status: **in progress** (branch `physio/mpddf-pilot`). Narrative, decisions, second opinions and
next steps: vault note `Subsystems/Physiology Decision Log.md` — start there. Nothing here is a deploy claim; every
number is experimental until the gates in §6 are met on Garmin data.

Why this exists: the WESAD artifact (`fatigue_wesad_v1.json`) scored LOSO AUROC **0.545** —
chance — because its label is lab *stress*, its sensor is the Empatica E4, and it has 15 subjects.
MPD-DF has physician-annotated *driving fatigue* on 50 participants with raw ECG. It fixes the
label, not the sensor. See `Subsystems/Physiology Fusion Approach.md` for the role physiology plays
in fusion (a confirming channel, never a stand-alone alarm).

## 1. The stream we must ultimately work on (Garmin FR265)

| Fact | Source |
|---|---|
| Built-in "Broadcast Heart Rate" carries **no RR** → unusable for HRV | `docs/garmin/STEP1_2_RESULTS.md` step 1 |
| A Connect IQ app (`garmin/rr_stream`) gets RR via `Sensor.registerSensorDataListener` (`:heartBeatIntervals`, 1 s period) | step 2 |
| Watch = BLE central, Pi = BLE peripheral (`garmin_receiver`, BlueZ/bless), service `0xFFF0`, 1 write/s, ≤20 B | `docs/packet_format.md` |
| Packet: version, flags, `seq`, `watch_ms`, `hr`, 0–5 × RR ms (uint16) | `docs/packet_format.md` |
| Pi receive time is the timestamp; `watch_ms`/`seq` only order packets and find gaps | `docs/packet_format.md` |
| **About half of the 1 s batches carry no RR**; window coverage was 0.3–0.9 in the 5-min test | `STEP1_2_RESULTS.md` |
| Beats either side of a silence are not neighbours; RMSSD/pNN50 need ≥10 true pairs | `garmin_hrv.py` |
| Features = `FeatureSnapshot.model_features()`: `mean_hr_bpm, hr_slope_bpm_per_min, median_ibi_ms, log_rmssd, sdnn_ms, pnn50, cvnn` from a 60 s window every 5 s; state `VALID/DEGRADED` only, else `null` | `garmin_hrv.py` |
| No reference (chest strap) recording yet, so Garmin RR accuracy is **unverified**; wrist motion while steering is **unmeasured** | `STEP1_2_RESULTS.md` |

## 2. MPD-DF facts (verified from the paper and files, not assumed)

- 50 participants, 2 h simulated driving, CC BY 4.0. figshare raw DOI `10.6084/m9.figshare.28455737`
  (code: `github.com/ljyTota/MPD-DF`). We use only `MPDDF_raw_NN_PSG.edf` (ECG @ 1024 Hz) +
  `MPDDF_raw_NN_Annotation.txt`; the 230 MB EEG files are not needed (50 subjects ≈ 1.1 GB).
- Labels are physician ratings **from EEG**: 0 wake, 1 fatigue1 (alpha onset), 2 drowsy,
  3/4 sleep N1/N2; 8/9 signal abnormality / severe artifacts. They hold per second until the next
  annotation line. Alignment = authors' `DataAlign.py` convention (clock time vs EDF `meas_date`).
- Facial video is **not** public → no camera+HRV joint training from this dataset.

## 3. Domain gaps between MPD-DF and the Garmin stream

| Gap | Effect | Planned handling |
|---|---|---|
| Chest ECG vs wrist optical RR | Different timing noise, no motion model | Step 5: degrade RR to Garmin shape; Step 8: validate on real Garmin |
| Continuous beats vs ~50% empty batches | Features come from a much easier signal | Step 5: replay dropout masks measured from real Garmin logs |
| ms-precise R peaks vs ~1 ms-quantised PPG RR | Mostly benign; RMSSD is sensitive | Step 5: add jitter at the level measured against a reference |
| EEG-derived label ≠ eyelid/behaviour | Label noise | Report 5-level and binary; keep fusion as confirm-only |
| Fatigue rises with time-on-task | A model can "predict" fatigue from the clock | Step 4: time-only control model; HRV must beat it |
| Few subjects ever reach label ≥2 | LOSO unreliable | Report per-subject AUROC over subjects with both classes only |

## 4. Steps

| # | Step | State |
|---|---|---|
| 1 | Verify dataset suitability from paper + figshare listing | **done** |
| 2 | `tools/mpddf_pilot.py`: ECG → R peaks → RR → the *same* `RrHrv` 60 s windows → features + per-window label | **done** |
| 3 | 5-participant pilot | **done, inconclusive**: only 2/5 subjects reach label ≥2 (S02: 86 windows, S04: 495); LOSO with one positive subject in training is meaningless (pooled AUROC 0.06 is a between-person artifact) |
| 3b | Fix found on the way: feed beats and compute windows as they stream (feeding everything first left `RrHrv` with its last 120 s only: 68 windows instead of ~6,300) | **done** |
| 4 | Full 50-subject LOSO: LogReg + RandForest, raw vs 5-min-baseline-normalised, **plus a time-on-task-only control** | **done** (clean ECG): see §7. HRV carries signal but adds ~nothing beyond time-on-task |
| 5 | **Garmin-ify** the RR before computing features: drop beats with burst/silence masks sampled from real Garmin CSV logs, add timing jitter; re-run Step 4 on degraded data | not started — **needs Garmin logs** |
| 6 | Evaluate the original 5 levels (ordinal) as well as binary | not started |
| 7 | Export JSON artifact (`tools/train_model.py` format) only if §6 gates pass; wire to `garmin_receiver --model` | blocked on 4–6 |
| 8 | Real-sensor validation: Garmin RR vs chest strap on a person at rest and while "steering"; then face-aligned Tier 1 logging | blocked on hardware |

## 5. What is needed

**From you (blocking):**
1. **Garmin RR session logs** — the `logs/garmin_rr_*.csv` files on the Pi (or the 5-min one
   referenced in `STEP1_2_RESULTS.md`). Step 5 needs them to measure real dropout and burst
   statistics. The more situations (rest, arm moving, wheel-turning motion), the better.
2. **A chest strap (e.g. Polar H10) or any ECG reference** for one 10–20 min session with the
   watch, to measure Garmin RR error. Without it Step 8 is not possible.
3. **Pi/watch availability** for a few sessions, and a decision on who tags drowsy/normal when we
   later log face-aligned data (Tier 1).
4. **A decision on the target**: binary "wake vs label ≥2" (my default; label 1 dropped as
   ambiguous) or also "wake vs ≥1". Fusion only needs a confirm signal, so I default to ≥2.

**From me / the machine (done or available):** MPD-DF raw ECG + labels for all 50 participants in
`data/mpddf/` (gitignored), venv `~/.venvs/mpddf` (numpy, scipy, scikit-learn, mne, neurokit2).

## 6. Pre-registered gates (decided before seeing the full result)

Continue to export (Step 7) only if **all** hold on the Garmin-degraded data (Step 5):

- mean per-subject LOSO AUROC ≥ **0.65** over subjects with both classes, and ≥ 70% of those
  subjects above 0.5;
- beats the time-on-task-only control by ≥ 0.05 AUROC;
- precision at the operating threshold is high enough to serve as a *confirm* gate (target set
  with fusion replays, not from this dataset alone).

If it fails, the honest outcome is: physiology stays a trend/baseline-deviation channel with no
fatigue classifier claim, and the report says so with this evidence.

## 7. Results

### Full run: 50 subjects, clean ECG (no Garmin degradation yet)

66,454 windows (60 s, every 5 s, same `RrHrv` features as the Pi). Target wake (0) vs label ≥ 2;
label 1 dropped; windows ≥ 80 % one label and free of 8/9. 50,379 windows, 3,154 positive (6.3 %).
Only **34 of 50** subjects ever reach label ≥ 2 and can be scored. Metric = AUROC *within each
held-out subject* (pooled AUROC is dominated by between-person offsets and is shown only for
completeness). Leave-one-subject-out throughout.

| Model | Features | per-subject AUROC mean / median | subjects > 0.5 | pooled AUROC |
|---|---|---|---|---|
| LogReg | raw | 0.689 / 0.640 | 27/34 | 0.430 |
| RandForest | raw | 0.530 / 0.515 | 19/34 | 0.404 |
| LogReg | baseline-normalised (first 5 min) | **0.719 / 0.817** | 26/34 | 0.633 |
| RandForest | baseline-normalised | 0.641 / 0.628 | 24/34 | 0.564 |

**Time-on-task control** (LogReg, same protocol):

| Features | per-subject AUROC mean / median | subjects > 0.5 |
|---|---|---|
| time only (hours into the drive) | **0.836 / 0.951** | 31/34 |
| HRV only (baseline-normalised) | 0.719 / 0.817 | 26/34 |
| HRV + time | 0.842 / 0.931 | 31/34 |

Reading it:

- Unlike WESAD (0.545), HRV does carry a real within-person signal for this label: 0.72 mean,
  and baseline normalisation helps (+0.03 LogReg, +0.11 RandForest). Logistic regression beats a
  random forest, consistent with the project's choice of logistic.
- **But the clock alone beats HRV (0.836 vs 0.719), and HRV adds only +0.006 on top of it.** In
  this protocol fatigue labels rise steadily over the 2 h drive, so "later = more fatigued" is a
  strong predictor and HRV (which drifts with time too) may largely be a proxy for it.
- Gate §6 "beats time-only by ≥ 0.05": **not met** (0.842 vs 0.836), already on clean ECG. Garmin
  degradation (Step 5) can only make HRV worse.
- Caveats: AUROC is rank-based within a subject, not a calibrated confirm-gate precision; the
  time-only control is a property of this lab protocol (sleep-deprived 2 h drive), real drives may
  not be that clock-aligned; and time-on-task is not a physiological signal, so it does not
  support the "HRV confirms drowsiness" claim.

What this means for the plan: HRV-only fatigue classification is **not yet justified**. The
useful, honest result is that physiology is informative *relative to the person's own baseline*
and does not add beyond elapsed driving time. Remaining checks before giving up on the model:
(a) test whether HRV adds beyond time within *time-matched* windows (compare wake vs fatigue at
the same elapsed time), (b) Step 5 degradation, (c) ordinal five-level target (Step 6).


### Are we dependent on RR? (ablation, same protocol, baseline-normalised LogReg)

| Features | per-subject AUROC mean / median | subjects > 0.5 |
|---|---|---|
| HR only (mean HR + HR slope; no RR needed) | **0.759 / 0.845** | 28/34 |
| HRV only (RMSSD, SDNN, pNN50, CVNN; needs RR) | 0.738 / 0.838 | 27/34 |
| HR + HRV | 0.725 / 0.825 | 26/34 |
| HR + time | 0.843 / 0.960 | 31/34 |

On clean ECG, HR alone does as well as HRV, so the fatigue signal does not depend on RR. The
time-on-task caveat above applies equally to HR. Caveat: this HR is ECG-derived; wrist optical HR
is noisier, so it needs the same Garmin-degradation check (Step 5).


### Plain metrics, quick fixes, and uncertainty (2026-11-20)

HR-only, baseline-normalised LogReg, LOSO, all 50,379 windows (6.3 % positive):

| Threshold | Accuracy | Recall | Precision | False-alarm rate |
|---|---|---|---|---|
| 0.5 | 70.1 % | 65.6 % | 12.9 % | 29.6 % |
| 0.7 | 89.8 % | 14.9 % | 15.9 % | 5.2 % |
| 0.9 | 93.6 % | 3.6 % | 39.2 % | 0.4 % |

"Never positive" baseline accuracy: 93.7 %.

At a 5 % false-alarm rate: HR 60 s recall 13.9 % / precision 16.4 %; + 5/15-min HR trends
15.9 % / 18.4 %; + HRV trends 14.7 % / 17.2 %; + 5-min output persistence 8.6 % / 11.0 %;
time only 31.0 % / 30.5 %.

Paired bootstrap over the 34 subjects (20,000 resamples, seed 42; Codex, reproduced by Claude):
baseline-normalised − raw = +0.031 AUROC, 95 % CI [−0.027, +0.094], 19/34 improved, Wilcoxon
p = 0.436. Subjects already at label ≥ 1 inside their 5-min baseline: 4, 9, 13, 22.
Known leak: `baseline_normalise` also scores the calibration windows themselves.

Breathing features (`tools/mpddf_resp.py` → `data/mpddf_resp.csv`): extracted, **not evaluated**.

## 8. Reproduce

```bash
cd models/physiology
python3 -m venv ~/.venvs/mpddf && ~/.venvs/mpddf/bin/pip install numpy scipy scikit-learn mne neurokit2 pandas
# data: figshare 28455737, *_PSG.edf + *_Annotation.txt into data/mpddf/
~/.venvs/mpddf/bin/python tools/mpddf_pilot.py --data data/mpddf --subjects 1-50 --evaluate
```

## §9 Shadow score (hr_shadow_mpddf_v1)

This score is logged only next to alert decisions with weight 0, never acted on, and its
weight is raised only if a paired camera + watch test shows value.

`tools/mpddf_score.py` exports `models/hr_shadow_mpddf_v1.json` in the existing logistic
format, with exactly `hr_delta_bpm` and `hr_trend_bpm_per_10min`. Delta subtracts the median
HR of **all** subject windows ending at or before first `t_s` + 300 s. Trend is least-squares
HR slope over (t_s − 600, t_s], multiplied by 600, requiring at least 24 windows. Both are
computed before label/purity filtering. Windows through the baseline endpoint are excluded
from fitting and evaluation; retained labels are 0 versus 2/3/4, purity ≥ 0.8, with finite
features. No additional quality filter is applied. These ECG-derived 60 s averages approximate
the live watch features; they do not reproduce its one-second sampling or quality gates.

The input has 66,454 windows from **49** subject IDs (42 is absent), despite §7's description
of 50 participants. Subjects 26 and 38 have no eligible windows after exclusions, leaving
47 subjects for LOSO and the final fit; 34 have both classes for within-subject AUROC.
Both models use identical windows and fold-local StandardScaler + balanced LogisticRegression
(default C=1, lbfgs, max_iter=1000, random_state=0). The final HR model fits all eligible
subjects. The JSON records full-precision metrics, per-subject AUROCs, input SHA-256 and
numpy/pandas/scikit-learn versions; extra metadata is accepted by the unchanged loader.

Reproduce from `models/physiology/` (reads the external CSV; does not copy it):

```bash
PYTHONPATH=src /home/teamacs/.venvs/mpddf/bin/python tools/mpddf_score.py
```

Printed summary (rates are fractions; false-alarm rate = FP / (FP + TN), per window):

```text
hr_shadow_mpddf_v1: LOSO, baseline windows excluded
Eligible: 47504 windows; 3154 positive; 47 subjects
Paired subject bootstrap: seed 42; 5000 resamples; percentile 95% CI
HR shadow: AUROC mean 0.761022, median 0.840791, 95% CI [0.678355, 0.838278]; subjects > 0.5: 28/34
  Pooled at p >= 0.7: precision 0.171032, recall 0.175967, false-alarm rate 0.060654
  TN=41660, FP=2690, FN=2599, TP=555
Time only (hours): AUROC mean 0.824221, median 0.947321, 95% CI [0.743675, 0.897373]; subjects > 0.5: 31/34
  Pooled at p >= 0.7: precision 0.247312, recall 0.313570, false-alarm rate 0.067869
  TN=41340, FP=3010, FN=2165, TP=989
HR minus time: mean AUROC difference -0.063200, paired 95% CI [-0.145684, 0.015692]
Export: hr_shadow_mpddf_v1; loader/sklearn probability parity passed
Use: logged only; weight 0; never acted on
```

The percentile bootstrap resamples the same 34 subject IDs for both models (5,000 draws,
seed 42), preserving pairing for the difference. It estimates uncertainty across held-out
subjects conditional on fitted LOSO predictions, without refitting bootstrap folds; it does
not establish watch-domain performance or probability calibration. Overlapping windows are
not independent trials, and false-alarm rate is not alarms per hour.

On clean ECG the AUROC ≥ 0.65 and ≥ 70% above-chance numerical criteria hold (28/34), but
beating time-only by ≥ 0.05 fails. The paired difference CI includes zero. §6's actual
Garmin-degraded validation and operating-precision gates remain unmet; this shadow export
does not authorize deployment as an alert input or change runtime wiring.
