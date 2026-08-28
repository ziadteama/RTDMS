"""Train and export the small deployment Logistic Regression artifact.

The input CSV must include one row per feature window, a subject identifier, a
binary label, and the feature columns named by ``--features``.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_model", type=Path)
    parser.add_argument("--subject-column", default="subject_id")
    parser.add_argument("--label-column", default="label")
    parser.add_argument(
        "--features",
        nargs="+",
        default=[
            "mean_hr_bpm",
            "hr_slope_bpm_per_min",
            "median_ibi_ms",
            "log_rmssd",
            "sdnn_ms",
            "pnn50",
            "cvnn",
        ],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score
        from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as error:
        raise SystemExit("Install training dependencies with: pip install -e '.[train]'") from error

    with args.input_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("input CSV has no rows")

    required = [args.subject_column, args.label_column, *args.features]
    missing = sorted(set(required) - set(rows[0]))
    if missing:
        raise SystemExit(f"input CSV is missing columns: {', '.join(missing)}")

    features = np.asarray(
        [[float(row[name]) for name in args.features] for row in rows], dtype=float
    )
    labels = np.asarray([int(row[args.label_column]) for row in rows], dtype=int)
    groups = np.asarray([row[args.subject_column] for row in rows])
    if set(labels) - {0, 1}:
        raise SystemExit("labels must be binary 0 or 1")
    if len(set(groups)) < 2:
        raise SystemExit("at least two subjects are required for leave-one-subject-out validation")

    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(max_iter=1_000, class_weight="balanced", random_state=0),
            ),
        ]
    )
    probabilities = cross_val_predict(
        pipeline,
        features,
        labels,
        groups=groups,
        cv=LeaveOneGroupOut(),
        method="predict_proba",
    )[:, 1]
    metrics: dict[str, float] = {
        "auroc": float(roc_auc_score(labels, probabilities)),
        "average_precision": float(average_precision_score(labels, probabilities)),
        "balanced_accuracy_at_0_5": float(balanced_accuracy_score(labels, probabilities >= 0.5)),
    }

    pipeline.fit(features, labels)
    scaler = pipeline.named_steps["scaler"]
    classifier = pipeline.named_steps["classifier"]
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "version": "unreleased",
        "feature_names": args.features,
        "means": [float(value) for value in scaler.mean_],
        "scales": [float(value) for value in scaler.scale_],
        "coefficients": [float(value) for value in classifier.coef_[0]],
        "intercept": float(classifier.intercept_[0]),
        "threshold": 0.5,
        "validation": metrics,
        "subjects": int(len(set(groups))),
    }
    args.output_model.parent.mkdir(parents=True, exist_ok=True)
    args.output_model.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
