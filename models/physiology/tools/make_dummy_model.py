"""Generate a deliberately fake, untrained model artifact for pipeline testing.

The artifact exercises the load, validate, quality-gate, and suppress path in
``PhysiologyService`` without making any claim about fatigue: every coefficient
and the intercept are zero, so ``LogisticModel.probability`` returns a constant
0.5 for every input. It is not a trained model and must never be deployed.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dms_physiology.features import FeatureSnapshot

VERSION = "dummy-untrained-DO-NOT-DEPLOY"
WARNING = (
    "Untrained artifact for pipeline testing only. "
    "Carries no predictive validity. Never deploy."
)


def feature_names() -> list[str]:
    """Read the runtime feature contract so the artifact can never drift from it.

    ``LogisticModel.probability`` raises on any name mismatch, so the names are
    taken from ``FeatureSnapshot.model_features`` rather than hardcoded.
    """

    snapshot = FeatureSnapshot(
        mean_hr_bpm=0.0,
        hr_slope_bpm_per_min=0.0,
        median_ibi_ms=0.0,
        rmssd_ms=0.0,
        sdnn_ms=0.0,
        pnn50=0.0,
        cvnn=0.0,
        valid_interval_count=0,
        artifact_fraction=0.0,
    )
    return list(snapshot.model_features())


def build_artifact() -> dict[str, Any]:
    names = feature_names()
    return {
        "schema_version": 1,
        "version": VERSION,
        "warning": WARNING,
        "feature_names": names,
        "means": [0.0] * len(names),
        "scales": [1.0] * len(names),
        "coefficients": [0.0] * len(names),
        "intercept": 0.0,
        "threshold": 0.5,
        "calibration": None,
        "dataset_fingerprint": None,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="destination JSON path")
    parser.add_argument(
        "--not-a-trained-model",
        action="store_true",
        help="required acknowledgement that this artifact has no predictive validity",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.not_a_trained_model:
        raise SystemExit(
            "refusing to run without --not-a-trained-model: this tool emits an untrained "
            "artifact whose output is a constant 0.5 and which has no predictive validity"
        )
    out: Path = args.out.resolve()
    if "models" in out.parent.parts:
        raise SystemExit(
            f"refusing to write inside a 'models' directory: {out}\n"
            "models/ is COPY'd into the Docker runtime stage, so a fake artifact placed "
            "there would ship in the deployable image and a meaningless fatigue score "
            "could reach the fusion layer. Write to a scratch path outside models/ instead."
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_artifact(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote untrained artifact ({VERSION}) to {out}")


if __name__ == "__main__":
    main()
