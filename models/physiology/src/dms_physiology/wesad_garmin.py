"""Offline WESAD (or synthetic) → RR → Garmin ``RrHrv`` feature windows.

Training rows use the same feature definition as the live Garmin path
(``RrHrv`` / ``FeatureSnapshot.model_features``), not the MAX30102 PPG peak service.
Prefer Empatica ``IBI.csv`` when present; otherwise recover RR from wrist BVP peaks.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.signal import find_peaks

from .features import FeatureSnapshot
from .garmin_hrv import UPDATE_S, WINDOW_S, HrvSnapshot, HrvState, RrHrv
from .garmin_rr import RrPacket, SequenceTracker
from .model import LogisticModel
from .signal import StreamingBandpass

# WESAD chest ECG / wrist E4 label IDs (Schmidt et al.)
WESAD_BASELINE = 1
WESAD_STRESS = 2
WESAD_AMUSEMENT = 3
BVP_HZ = 64.0
LABEL_HZ = 700.0  # chest-labelling rate in the official .pkl


def rr_from_bvp(bvp: NDArray[np.floating], sample_rate_hz: float = BVP_HZ) -> list[float]:
    """Recover RR intervals (ms) from a wrist BVP trace. Dataset prep only."""

    values = np.asarray(bvp, dtype=np.float64).reshape(-1)
    if values.size < int(sample_rate_hz):
        return []
    high = min(5.0, sample_rate_hz / 2 - 0.1)
    filt = StreamingBandpass(sample_rate_hz, lowcut_hz=0.5, highcut_hz=high)
    filtered = np.asarray(filt.process(values.astype(np.float32)), dtype=np.float64)
    # Empatica BVP is AC; systolic peaks may be + or - — take the stronger polarity.
    pos_energy = np.square(np.maximum(filtered, 0.0))
    neg_energy = np.square(np.maximum(-filtered, 0.0))
    energy = pos_energy if float(np.sum(pos_energy)) >= float(np.sum(neg_energy)) else neg_energy
    refractory = max(int(round(sample_rate_hz * 0.3)), 1)
    height = float(np.median(energy) + 0.35 * np.std(energy))
    prominence = max(float(np.std(energy)) * 0.2, float(np.finfo(np.float32).eps))
    peaks, _ = find_peaks(
        energy,
        height=max(height, float(np.finfo(np.float32).eps)),
        distance=refractory,
        prominence=prominence,
    )
    if peaks.size < 2:
        return []
    intervals = np.diff(peaks.astype(np.float64)) * (1000.0 / sample_rate_hz)
    return [float(x) for x in intervals if math.isfinite(x)]


def feed_rr(hrv: RrHrv, rr_ms: Sequence[float], *, t0: float = 100.0) -> float:
    """Push one RR per packet into ``RrHrv`` via ``SequenceTracker``. Returns last rx time."""

    tracker = SequenceTracker()
    t = t0
    seq = 0
    watch_ms = 5_000_000
    for value in rr_ms:
        rr = int(round(float(value)))
        if rr <= 0:
            continue
        t += rr / 1000.0
        watch_ms = (watch_ms + rr) % (1 << 32)
        packet = RrPacket(seq=seq % 65536, watch_ms=watch_ms, hr_bpm=None, rr_ms=(rr,))
        hrv.add(tracker.accept(packet, t, 1.8e9 + t))
        seq += 1
    return t


def windows_from_rr(
    rr_ms: Sequence[float],
    *,
    label: int,
    subject_id: str,
    update_s: float = UPDATE_S,
    t0: float = 100.0,
) -> list[dict[str, float | int | str]]:
    """Replay RR through ``RrHrv``; keep VALID/DEGRADED windows as model-feature rows."""

    if len(rr_ms) < 40:
        return []
    hrv = RrHrv()
    t_end = feed_rr(hrv, rr_ms, t0=t0)
    rows: list[dict[str, float | int | str]] = []
    # First compute after one full window of beats, then every update_s.
    t = t0 + WINDOW_S
    while t <= t_end + 1e-9:
        snap = hrv.compute(t)
        if snap.state in (HrvState.VALID, HrvState.DEGRADED) and snap.features is not None:
            row: dict[str, float | int | str] = {
                "subject_id": subject_id,
                "label": int(label),
                **{k: float(v) for k, v in snap.features.model_features().items()},
            }
            rows.append(row)
        t += update_s
    return rows


def label_series_for_bvp(
    chest_labels: NDArray[np.integer],
    bvp_len: int,
    *,
    label_hz: float = LABEL_HZ,
    bvp_hz: float = BVP_HZ,
) -> NDArray[np.int64]:
    """Resample WESAD chest labels (700 Hz) onto the BVP sample grid (64 Hz)."""

    labels = np.asarray(chest_labels, dtype=np.int64).reshape(-1)
    idx = np.minimum(
        (np.arange(bvp_len) * (label_hz / bvp_hz)).astype(int),
        labels.size - 1,
    )
    return np.asarray(labels[idx], dtype=np.int64)


def segment_rr_by_label(
    bvp: NDArray[np.floating],
    labels_on_bvp: NDArray[np.integer],
    *,
    sample_rate_hz: float = BVP_HZ,
) -> list[tuple[int, list[float]]]:
    """Return (wesad_label_id, rr_ms) for contiguous baseline/stress runs only."""

    labels = np.asarray(labels_on_bvp).reshape(-1)
    signal = np.asarray(bvp).reshape(-1)
    n = min(labels.size, signal.size)
    out: list[tuple[int, list[float]]] = []
    i = 0
    while i < n:
        lab = int(labels[i])
        j = i + 1
        while j < n and int(labels[j]) == lab:
            j += 1
        if lab in (WESAD_BASELINE, WESAD_STRESS):
            rr = rr_from_bvp(signal[i:j], sample_rate_hz=sample_rate_hz)
            if rr:
                out.append((lab, rr))
        i = j
    return out


def binary_label(wesad_label_id: int) -> int | None:
    """baseline→0, stress→1, else drop."""

    if wesad_label_id == WESAD_BASELINE:
        return 0
    if wesad_label_id == WESAD_STRESS:
        return 1
    return None


def load_wesad_subject(pkl_path: Path) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """Load wrist BVP and chest label vector from an official WESAD subject pickle."""

    import pickle

    with pkl_path.open("rb") as handle:
        data = pickle.load(handle, encoding="latin1")
    bvp = np.asarray(data["signal"]["wrist"]["BVP"], dtype=np.float64).reshape(-1)
    labels = np.asarray(data["label"], dtype=np.int64).reshape(-1)
    return bvp, labels


_QUEST_CONDITION = {
    "base": WESAD_BASELINE,
    "tsst": WESAD_STRESS,
    "fun": WESAD_AMUSEMENT,
}


def load_wesad_bvp_csv(bvp_path: Path) -> tuple[NDArray[np.float64], float]:
    """Load Empatica E4 ``BVP.csv`` (timestamp, Hz, then samples). Returns (signal, hz)."""

    with bvp_path.open(encoding="utf-8") as handle:
        next(handle, None)  # unix start
        hz_line = next(handle, "64")
        hz = float(str(hz_line).split(",")[0].strip() or BVP_HZ)
        values = [float(line.strip().split(",")[0]) for line in handle if line.strip()]
    return np.asarray(values, dtype=np.float64), hz


def load_wesad_ibi_csv(ibi_path: Path) -> list[tuple[float, float]]:
    """Load Empatica ``IBI.csv`` as ``(t_sec_from_start, rr_ms)`` pairs (skip header)."""

    out: list[tuple[float, float]] = []
    with ibi_path.open(encoding="utf-8") as handle:
        next(handle, None)  # unix start, "IBI"
        for line in handle:
            parts = [p.strip() for p in line.strip().split(",") if p.strip()]
            if len(parts) < 2:
                continue
            t_sec = float(parts[0])
            rr_ms = float(parts[1]) * 1000.0
            if math.isfinite(t_sec) and math.isfinite(rr_ms) and rr_ms > 0:
                out.append((t_sec, rr_ms))
    return out


def parse_quest_segments(quest_path: Path) -> list[tuple[int, float, float]]:
    """Return ``(wesad_label_id, start_sec, end_sec)`` for Base/TSST/Fun only."""

    order: list[str] = []
    starts: list[float] = []
    ends: list[float] = []
    with quest_path.open(encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line.startswith("#"):
                continue
            parts = [p.strip() for p in line.lstrip("#").split(";")]
            if not parts:
                continue
            key = parts[0].strip().upper()
            cells = [c for c in parts[1:] if c]
            if key == "ORDER":
                order = cells
            elif key == "START":
                starts = [float(c) for c in cells]
            elif key == "END":
                ends = [float(c) for c in cells]
    out: list[tuple[int, float, float]] = []
    n = min(len(order), len(starts), len(ends))
    for i in range(n):
        lab = _QUEST_CONDITION.get(order[i].strip().lower())
        if lab is None:
            continue
        out.append((lab, starts[i] * 60.0, ends[i] * 60.0))
    return out


def labels_from_quest(
    quest_path: Path,
    bvp_len: int,
    *,
    sample_rate_hz: float = BVP_HZ,
) -> NDArray[np.int64]:
    """Map ``S*_quest.csv`` START/END minutes onto a BVP-length label vector."""

    labels = np.zeros(bvp_len, dtype=np.int64)
    for lab, start_s, end_s in parse_quest_segments(quest_path):
        i0 = max(0, int(round(start_s * sample_rate_hz)))
        i1 = min(bvp_len, int(round(end_s * sample_rate_hz)))
        if i1 > i0:
            labels[i0:i1] = lab
    return labels


def segment_ibi_by_quest(
    ibi_rows: Sequence[tuple[float, float]],
    quest_path: Path,
) -> list[tuple[int, list[float]]]:
    """Slice Empatica IBI beats into Base/TSST RR lists using quest times."""

    out: list[tuple[int, list[float]]] = []
    for lab, start_s, end_s in parse_quest_segments(quest_path):
        rr = [rr_ms for t_sec, rr_ms in ibi_rows if start_s <= t_sec <= end_s]
        if rr:
            out.append((lab, rr))
    return out


def windows_from_bvp_labels(
    bvp: NDArray[np.floating],
    labels_on_bvp: NDArray[np.integer],
    subject_id: str,
    *,
    sample_rate_hz: float = BVP_HZ,
) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    for lab_id, rr in segment_rr_by_label(bvp, labels_on_bvp, sample_rate_hz=sample_rate_hz):
        binary = binary_label(lab_id)
        if binary is None:
            continue
        rows.extend(windows_from_rr(rr, label=binary, subject_id=subject_id))
    return rows


def windows_from_wesad_subject(
    pkl_path: Path, subject_id: str | None = None
) -> list[dict[str, float | int | str]]:
    sid = subject_id or pkl_path.stem
    bvp, labels = load_wesad_subject(pkl_path)
    on_bvp = label_series_for_bvp(labels, bvp.size)
    return windows_from_bvp_labels(bvp, on_bvp, sid)


def windows_from_wesad_e4(
    e4_dir: Path,
    quest_path: Path,
    subject_id: str | None = None,
) -> list[dict[str, float | int | str]]:
    """E4 folder + quest: prefer ``IBI.csv`` (Garmin-like RR); else BVP peak recovery."""

    sid = subject_id or e4_dir.parent.name
    ibi_path = e4_dir / "IBI.csv"
    rows: list[dict[str, float | int | str]] = []
    if ibi_path.is_file() and ibi_path.stat().st_size > 0:
        for lab_id, rr in segment_ibi_by_quest(load_wesad_ibi_csv(ibi_path), quest_path):
            binary = binary_label(lab_id)
            if binary is None:
                continue
            rows.extend(windows_from_rr(rr, label=binary, subject_id=sid))
        if rows:
            return rows
    bvp_path = e4_dir / "BVP.csv"
    if not bvp_path.is_file():
        return rows
    bvp, hz = load_wesad_bvp_csv(bvp_path)
    on_bvp = labels_from_quest(quest_path, bvp.size, sample_rate_hz=hz)
    return windows_from_bvp_labels(bvp, on_bvp, sid, sample_rate_hz=hz)


def synthetic_subject_rr(
    *,
    subject: str,
    label: int,
    n_beats: int = 200,
    seed: int = 0,
) -> list[float]:
    """Garmin-shaped RR: stress → higher mean HR / lower variability."""

    rng = np.random.default_rng(seed)
    if label == 0:
        mean, swing, noise = 900.0, 45.0, 12.0
    else:
        mean, swing, noise = 700.0, 18.0, 6.0
    k = np.arange(n_beats)
    rr = mean + swing * np.sin(2 * np.pi * k / 7.0) + rng.normal(0.0, noise, n_beats)
    return [float(x) for x in np.clip(np.round(rr), 400, 1500)]


def synthetic_training_rows(subjects: int = 8, seed: int = 0) -> list[dict[str, float | int | str]]:
    """Multi-subject baseline/stress windows through ``RrHrv`` (no WESAD files needed)."""

    rows: list[dict[str, float | int | str]] = []
    for i in range(subjects):
        sid = f"SYN{i + 1:02d}"
        for label in (0, 1):
            rr = synthetic_subject_rr(subject=sid, label=label, seed=seed + i * 10 + label)
            rows.extend(windows_from_rr(rr, label=label, subject_id=sid, t0=100.0 + i))
    return rows


def fatigue_probability(
    snap: HrvSnapshot,
    model: LogisticModel | None,
) -> tuple[float | None, str | None]:
    """Same gate as PPG service: only VALID/DEGRADED with finite features invoke the model."""

    version = None if model is None else model.version
    if model is None or snap.features is None:
        return None, version
    if snap.state not in (HrvState.VALID, HrvState.DEGRADED):
        return None, version
    try:
        values = snap.features.model_features()
        if not all(math.isfinite(v) for v in values.values()):
            return None, version
        return float(model.probability(values)), version
    except (TypeError, ValueError):
        return None, version


def enrich_hrv_dict(
    snap: HrvSnapshot,
    model: LogisticModel | None,
) -> dict[str, object]:
    """``HrvSnapshot.to_dict()`` plus gated ``fatigue_probability`` / ``model_version``."""

    payload = snap.to_dict()
    prob, version = fatigue_probability(snap, model)
    payload["fatigue_probability"] = None if prob is None else round(prob, 4)
    payload["model_version"] = version
    return payload


def write_windows_csv(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    import csv

    materialised = list(rows)
    if not materialised:
        raise ValueError("no feature windows to write")
    fieldnames = ["subject_id", "label", *FeatureSnapshot(
        mean_hr_bpm=0.0,
        hr_slope_bpm_per_min=0.0,
        median_ibi_ms=0.0,
        rmssd_ms=0.0,
        sdnn_ms=0.0,
        pnn50=0.0,
        cvnn=0.0,
        valid_interval_count=0,
        artifact_fraction=0.0,
    ).model_features()]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in materialised:
            writer.writerow({name: row[name] for name in fieldnames})
    return len(materialised)
