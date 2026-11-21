"""MPD-DF feasibility pilot: can the Pi's 7 HR/HRV features predict physician-annotated fatigue?

Data: MPD-DF raw release (figshare 10.6084/m9.figshare.28455737, CC BY 4.0). Per participant we
need only ``MPDDF_raw_NN_PSG.edf`` (ECG @1024 Hz, ~23 MB) and ``MPDDF_raw_NN_Annotation.txt``.
Labels are EEG-based physician ratings: 0 wake, 1 fatigue1 (alpha onset), 2 drowsy,
3/4 N1/N2 sleep; 8/9 = signal abnormality / severe artifacts (windows touching them are dropped).

Pipeline: ECG -> R peaks -> RR ms -> the same ``RrHrv`` 60 s window the Garmin path uses ->
``FeatureSnapshot.model_features()`` -> per-window label -> leave-one-subject-out evaluation.

    python tools/mpddf_pilot.py --data data/mpddf --subjects 1-5 --out data/mpddf_windows.csv
    python tools/mpddf_pilot.py --windows data/mpddf_windows.csv --evaluate

Dataset prep + evaluation only; nothing here enters the runtime path.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dms_physiology.garmin_hrv import UPDATE_S, WINDOW_S, HrvState, RrHrv  # noqa: E402
from dms_physiology.garmin_rr import RrPacket, SequenceTracker  # noqa: E402

FEATURES = ["mean_hr_bpm", "hr_slope_bpm_per_min", "median_ibi_ms", "log_rmssd",
            "sdnn_ms", "pnn50", "cvnn"]
BAD_LABELS = {8, 9}
LABEL_NAMES = {"Signal Abnormality": 8, "Severe Artifacts": 9}


def parse_annotation(path: Path) -> tuple[list[int], list[int]]:
    """(clock seconds-of-day, label) pairs; a label holds until the next line."""
    ts, lab = [], []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        h, m, s = (int(x) for x in parts[0].split(":"))
        raw = parts[-1].strip()
        ts.append(h * 3600 + m * 60 + s)
        lab.append(LABEL_NAMES.get(raw, int(raw) if re.fullmatch(r"-?\d+", raw) else -1))
    return ts, lab


def load_ecg(edf: Path) -> tuple[np.ndarray, float, int]:
    import mne

    raw = mne.io.read_raw_edf(edf, include=["ECG"], preload=True, verbose=False)
    d = raw.info["meas_date"]
    start = d.hour * 3600 + d.minute * 60 + d.second  # same convention as the authors' DataAlign.py
    return raw.get_data()[0], float(raw.info["sfreq"]), start


def rpeaks(ecg: np.ndarray, fs: float) -> np.ndarray:
    import neurokit2 as nk

    sig = nk.ecg_clean(ecg * 1e3 if np.abs(ecg).max() < 1 else ecg, sampling_rate=fs)
    _, info = nk.ecg_peaks(sig, sampling_rate=fs, correct_artifacts=False)
    return np.asarray(info["ECG_R_Peaks"], dtype=float) / fs  # seconds


def per_second_labels(ts: list[int], lab: list[int], rec_start: int, n_sec: int) -> np.ndarray:
    out = np.full(n_sec, -1, dtype=int)
    for i, t0 in enumerate(ts):
        a = max(t0 - rec_start, 0)
        b = (ts[i + 1] - rec_start) if i + 1 < len(ts) else n_sec
        if b > a:
            out[a:min(b, n_sec)] = lab[i]
    return out


def windows_for_subject(sid: int, data: Path) -> pd.DataFrame:
    ecg, fs, rec_start = load_ecg(data / f"MPDDF_raw_{sid:02d}_PSG.edf")
    ts, lab = parse_annotation(data / f"MPDDF_raw_{sid:02d}_Annotation.txt")
    n_sec = int(len(ecg) / fs)
    labels = per_second_labels(ts, lab, rec_start, n_sec)
    peaks = rpeaks(ecg, fs)
    rr = np.diff(peaks) * 1000.0
    print(f"  S{sid:02d}: {n_sec/60:.0f} min, {len(peaks)} beats, median HR "
          f"{60000/np.median(rr):.1f} bpm, rr<300|>2000ms: {np.mean((rr<300)|(rr>2000)):.1%}")

    t0 = 1000.0  # arbitrary monotonic origin; beat k "arrives" when it ends
    hrv, tracker = RrHrv(), SequenceTracker()
    rows = []
    next_t = peaks[1] + WINDOW_S  # stream like the live receiver: compute every UPDATE_S as beats arrive

    def emit(t: float) -> None:
        snap = hrv.compute(t0 + t)
        sec = int(t)
        win = labels[max(sec - int(WINDOW_S), 0):sec]
        if snap.state not in (HrvState.VALID, HrvState.DEGRADED) or not snap.features:
            return
        if not win.size or (win < 0).any() or (set(win.tolist()) & BAD_LABELS):
            return
        vals, counts = np.unique(win, return_counts=True)
        rows.append({"subject": sid, "t_s": sec, "label": int(vals[counts.argmax()]),
                     "purity": float(counts.max() / win.size),
                     "quality": snap.quality.state.value,
                     **{k: float(v) for k, v in snap.features.model_features().items()}})

    for seq, (t_end, v) in enumerate(zip(peaks[1:], rr, strict=True)):
        while next_t <= t_end:
            emit(next_t)
            next_t += UPDATE_S
        pkt = RrPacket(seq=seq % 65536, watch_ms=int(t_end * 1000) % (1 << 32),
                       hr_bpm=None, rr_ms=(int(round(v)),))
        hrv.add(tracker.accept(pkt, t0 + t_end, 1.8e9 + t_end))
    return pd.DataFrame(rows)


def parse_subjects(spec: str) -> list[int]:
    ids: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        ids += list(range(int(a), int(b or a) + 1))
    return ids


# ---------------------------------------------------------------- evaluation ------------------
def baseline_normalise(df: pd.DataFrame, minutes: float) -> pd.DataFrame:
    """z-score each subject's features against its own first `minutes` of windows."""
    out = df.copy()
    for sid, g in df.groupby("subject"):
        ref = g[g.t_s <= g.t_s.min() + minutes * 60]
        mu, sd = ref[FEATURES].mean(), ref[FEATURES].std().replace(0, 1e-9)
        out.loc[g.index, FEATURES] = (g[FEATURES] - mu) / sd
    return out


def loso(df: pd.DataFrame, make_model, cols: list[str] = FEATURES) -> tuple[float, float, np.ndarray]:
    from sklearn.metrics import average_precision_score, roc_auc_score

    subs = sorted(df.subject.unique())
    prob = np.full(len(df), np.nan)
    for s in subs:
        tr, te = df.subject != s, df.subject == s
        if df.loc[tr, "y"].nunique() < 2:
            continue
        m = make_model().fit(df.loc[tr, cols], df.loc[tr, "y"])
        prob[te.to_numpy()] = m.predict_proba(df.loc[te, cols])[:, 1]
    ok = ~np.isnan(prob)
    y = df.y.to_numpy()[ok]
    return roc_auc_score(y, prob[ok]), average_precision_score(y, prob[ok]), prob


def evaluate(df: pd.DataFrame, baseline_min: float, pos_min: int) -> None:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    print("\nlabel counts (windows) per subject:")
    print(pd.crosstab(df.subject, df.label).to_string())
    d = df[(df.purity >= 0.8) & ((df.label == 0) | (df.label >= pos_min))].copy()
    d["y"] = (d.label >= pos_min).astype(int)
    print(f"\ntarget: wake(0) vs label>={pos_min}; label 1 dropped; purity>=0.8 -> "
          f"{len(d)} windows, {int(d.y.sum())} positive, {d.y.mean():.1%} prevalence")
    both = [s for s, g in d.groupby("subject") if g.y.nunique() == 2]
    print(f"subjects with both classes: {both} of {sorted(d.subject.unique())}")
    if len(both) < 2:
        print("Too few subjects with both classes for a meaningful LOSO; expand the pilot.")
        return
    models = {
        "LogReg": lambda: make_pipeline(StandardScaler(), LogisticRegression(
            max_iter=2000, class_weight="balanced")),
        "RandForest": lambda: RandomForestClassifier(
            n_estimators=300, min_samples_leaf=5, class_weight="balanced",
            n_jobs=-1, random_state=0),
    }
    variants = {"raw features": d}
    # baseline uses the full unfiltered timeline, so normalise before filtering
    full = baseline_normalise(df, baseline_min)
    dn = full.loc[d.index].copy()
    dn["y"] = d.y
    variants[f"baseline-normalised ({baseline_min:g} min)"] = dn
    for vname, dv in variants.items():
        print(f"\n== {vname}")
        for mname, mk in models.items():
            auc, ap, prob = loso(dv.reset_index(drop=True), mk)
            ok = ~np.isnan(prob)
            per = []
            dvr = dv.reset_index(drop=True)
            for s in both:
                m = (dvr.subject == s).to_numpy() & ok
                if m.any() and dvr.y[m].nunique() == 2:
                    per.append(roc_auc_score(dvr.y[m], prob[m]))
            print(f"  {mname:10s} per-subject AUROC mean {np.mean(per):.3f} median {np.median(per):.3f} "
                  f"(n={len(per)} subjects, {sum(p > 0.5 for p in per)} above chance) | "
                  f"pooled AUROC {auc:.3f} AP {ap:.3f} vs prevalence {d.y.mean():.3f}")
    # Controls: fatigue labels rise with time-on-task, so a clock alone may score well.
    print("\n== controls (LogReg, LOSO, per-subject AUROC over subjects with both classes)")
    dvr = variants[f"baseline-normalised ({baseline_min:g} min)"].reset_index(drop=True)
    draw = d.reset_index(drop=True)
    dvr["t_s"] = draw["t_s"].to_numpy() / 3600.0
    for name, cols, frame in [("time only", ["t_s"], draw.assign(t_s=draw.t_s / 3600.0)),
                              ("HRV only (baseline-norm)", FEATURES, dvr),
                              ("HRV + time (baseline-norm)", FEATURES + ["t_s"], dvr)]:
        mk = models["LogReg"]
        _, _, prob = loso(frame, mk, cols)
        ok = ~np.isnan(prob)
        per = [roc_auc_score(frame.y[m], prob[m]) for s in both
               if (m := (frame.subject == s).to_numpy() & ok).any() and frame.y[m].nunique() == 2]
        print(f"  {name:28s} mean {np.mean(per):.3f} median {np.median(per):.3f} "
              f"({sum(p > 0.5 for p in per)}/{len(per)} above chance)")
    print("\nchance AUROC = 0.5. The WESAD model scored 0.545 LOSO.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/mpddf"))
    ap.add_argument("--subjects", default="1-5")
    ap.add_argument("--out", type=Path, default=Path("data/mpddf_windows.csv"))
    ap.add_argument("--windows", type=Path, help="evaluate from an existing windows CSV")
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--baseline-min", type=float, default=5.0)
    ap.add_argument("--pos-min", type=int, default=2, help="lowest label counted as fatigued")
    a = ap.parse_args()
    if a.windows:
        df = pd.read_csv(a.windows)
    else:
        print("building windows")
        df = pd.concat([windows_for_subject(s, a.data) for s in parse_subjects(a.subjects)],
                       ignore_index=True)
        df.to_csv(a.out, index=False)
        print(f"wrote {a.out}: {len(df)} windows")
    if a.evaluate or a.windows:
        evaluate(df, a.baseline_min, a.pos_min)


if __name__ == "__main__":
    main()
