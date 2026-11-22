"""Prepare, evaluate and export an offline MPD-DF HR shadow score; never runtime code."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from mpddf_pilot import loso
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from dms_physiology.hr_stream import BASELINE_S, BUFFER_S
from dms_physiology.model import LogisticModel

FEATURES = ["hr_delta_bpm", "hr_trend_bpm_per_10min"]
VERSION = "hr_shadow_mpddf_v1"
DEFAULT_INPUT = Path("/home/teamacs/RTDMS/models/physiology/data/mpddf_windows.csv")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "models" / f"{VERSION}.json"
THRESHOLD = 0.7


def rolling_trend(times: np.ndarray, hr: np.ndarray) -> np.ndarray:
    """Causal OLS on (t - 600, t], requiring at least 24 finite HR windows."""
    trend = np.full(len(times), np.nan)
    for i, end in enumerate(times):
        start = np.searchsorted(times, end - BUFFER_S, side="right")
        stop = np.searchsorted(times, end, side="right")
        x, y = times[start:stop], hr[start:stop]
        if len(x) < 24 or not np.isfinite(y).all():
            continue
        x = x - x.mean()
        denominator = x @ x
        if denominator > 0:
            trend[i] = BUFFER_S * (x @ (y - y.mean())) / denominator
    return trend


def prepare(windows: pd.DataFrame) -> pd.DataFrame:
    """Build features on ALL windows before label/purity/baseline exclusions."""
    frames = []
    for _, group in windows.groupby("subject", sort=True):
        group = group.sort_values("t_s").copy()
        times = group.t_s.to_numpy(dtype=float)
        hr = group.mean_hr_bpm.to_numpy(dtype=float)
        if not np.isfinite(times).all():
            raise ValueError("window times must be finite")
        baseline_end = times[0] + BASELINE_S
        baseline = group.loc[group.t_s <= baseline_end, "mean_hr_bpm"].median()
        group[FEATURES[0]] = hr - baseline
        group[FEATURES[1]] = rolling_trend(times, hr)
        group["after_baseline"] = times > baseline_end
        frames.append(group)
    full = pd.concat(frames, ignore_index=True)
    keep = full.after_baseline & (full.purity >= 0.8) & full.label.isin([0, 2, 3, 4])
    keep &= np.isfinite(full[FEATURES]).all(axis=1)
    eligible = full.loc[keep].copy().reset_index(drop=True)
    eligible["y"] = (eligible.label >= 2).astype(int)
    eligible["time_hours"] = eligible.t_s / 3600
    return eligible


def make_model():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced", random_state=0),
    )


def evaluate(data: pd.DataFrame, columns: list[str]) -> tuple[dict, np.ndarray]:
    _, _, probabilities = loso(data, make_model, columns)
    if not np.isfinite(probabilities).all():
        raise ValueError("LOSO could not score every window; check training class coverage")
    per_subject = {
        str(subject): float(roc_auc_score(group.y, probabilities[group.index]))
        for subject, group in data.groupby("subject", sort=True)
        if group.y.nunique() == 2
    }
    aucs = np.asarray(list(per_subject.values()))
    if len(aucs) < 2:
        raise ValueError("at least two subjects with both classes are required")
    predicted = probabilities >= THRESHOLD
    tn, fp, fn, tp = confusion_matrix(data.y, predicted, labels=[0, 1]).ravel()
    metrics = {
        "per_subject_auroc": per_subject,
        "mean_auroc": float(aucs.mean()),
        "median_auroc": float(np.median(aucs)),
        "subjects_above_0_5": int((aucs > 0.5).sum()),
        "subjects_with_both_classes": len(aucs),
        "precision": float(precision_score(data.y, predicted, zero_division=0)),
        "recall": float(recall_score(data.y, predicted, zero_division=0)),
        "false_alarm_rate": float(fp / (fp + tn)),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
    return metrics, aucs


def paired_bootstrap(hr: np.ndarray, time: np.ndarray) -> dict:
    """Percentile CIs: resample subjects, preserving HR/time pairing, not windows."""
    indices = np.random.default_rng(42).integers(0, len(hr), size=(5000, len(hr)))
    return {
        name: np.quantile(values[indices].mean(axis=1), [0.025, 0.975]).tolist()
        for name, values in {"hr": hr, "time": time, "hr_minus_time": hr - time}.items()
    }


def export(data: pd.DataFrame, source: Path, destination: Path, validation: dict) -> None:
    pipeline = make_model().fit(data[FEATURES], data.y)
    scaler, classifier = pipeline.steps[0][1], pipeline.steps[1][1]
    artifact = {
        "schema_version": 1,
        "version": VERSION,
        "feature_names": FEATURES,
        "means": scaler.mean_.tolist(),
        "scales": scaler.scale_.tolist(),
        "coefficients": classifier.coef_[0].tolist(),
        "intercept": float(classifier.intercept_[0]),
        "threshold": THRESHOLD,
        "validation": validation,
        "subjects": int(data.subject.nunique()),
        "windows": len(data),
        "metadata": {
            "intended_use": "logged only; fusion weight 0; never acted on",
            "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__,
            "bootstrap": "paired subjects; percentile 95%; seed 42; 5000 resamples",
            "false_alarm_rate": "FP / (FP + TN), pooled windows, not events per hour",
        },
    }
    destination.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    loaded = LogisticModel.from_json_file(destination)
    expected = pipeline.predict_proba(data[FEATURES])[:, 1]
    actual = np.array([loaded.probability(row) for row in data[FEATURES].to_dict("records")])
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def print_summary(data: pd.DataFrame, validation: dict) -> None:
    print(f"{VERSION}: LOSO, baseline windows excluded")
    print(f"Eligible: {len(data)} windows; {int(data.y.sum())} positive; "
          f"{data.subject.nunique()} subjects")
    print("Paired subject bootstrap: seed 42; 5000 resamples; percentile 95% CI")
    for key, name in [("hr", "HR shadow"), ("time", "Time only (hours)")]:
        result = validation[key]
        low, high = validation["bootstrap_ci"][key]
        print(f"{name}: AUROC mean {result['mean_auroc']:.6f}, "
              f"median {result['median_auroc']:.6f}, 95% CI [{low:.6f}, {high:.6f}]; "
              f"subjects > 0.5: {result['subjects_above_0_5']}/"
              f"{result['subjects_with_both_classes']}")
        print(f"  Pooled at p >= 0.7: precision {result['precision']:.6f}, "
              f"recall {result['recall']:.6f}, false-alarm rate {result['false_alarm_rate']:.6f}")
        counts = result["confusion"]
        print("  " + ", ".join(f"{key.upper()}={value}" for key, value in counts.items()))
    low, high = validation["bootstrap_ci"]["hr_minus_time"]
    difference = validation["hr"]["mean_auroc"] - validation["time"]["mean_auroc"]
    print(f"HR minus time: mean AUROC difference {difference:.6f}, "
          f"paired 95% CI [{low:.6f}, {high:.6f}]")
    print("Export: hr_shadow_mpddf_v1; loader/sklearn probability parity passed")
    print("Use: logged only; weight 0; never acted on")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data = prepare(pd.read_csv(args.windows))
    hr, hr_aucs = evaluate(data, FEATURES)
    time, time_aucs = evaluate(data, ["time_hours"])
    validation = {"hr": hr, "time": time, "bootstrap_ci": paired_bootstrap(hr_aucs, time_aucs)}
    export(data, args.windows, args.output, validation)
    print_summary(data, validation)


if __name__ == "__main__":
    main()
