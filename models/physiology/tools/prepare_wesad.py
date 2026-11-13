"""Build a Garmin-``RrHrv`` feature CSV from WESAD (or synthetic RR).

See ``docs/WESAD.md``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dms_physiology.wesad_garmin import (  # noqa: E402
    synthetic_training_rows,
    windows_from_wesad_e4,
    windows_from_wesad_subject,
    write_windows_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wesad-root",
        type=Path,
        default=ROOT / "data" / "WESAD",
        help="folder containing S*/S*.pkl or S*/S*_E4_Data/BVP.csv + quest",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "wesad_garmin_windows.csv",
        help="output CSV path",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="ignore WESAD files; emit multi-subject synthetic Garmin-shaped windows",
    )
    parser.add_argument("--subjects", type=int, default=8, help="synthetic subject count")
    return parser.parse_args()


def discover_pickles(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    found = sorted(root.glob("S*/S*.pkl"))
    if found:
        return found
    return sorted(root.glob("**/*.pkl"))


def discover_e4_subjects(root: Path) -> list[tuple[str, Path, Path]]:
    """Return (subject_id, e4_dir, quest_csv) for E4-only layouts."""

    if not root.is_dir():
        return []
    out: list[tuple[str, Path, Path]] = []
    for subject_dir in sorted(p for p in root.glob("S*") if p.is_dir()):
        sid = subject_dir.name
        quest = subject_dir / f"{sid}_quest.csv"
        e4_dirs = sorted(p for p in subject_dir.glob(f"**/{sid}_E4_Data") if p.is_dir())
        if not e4_dirs:
            e4_dirs = sorted(p for p in subject_dir.glob("**/*E4_Data") if p.is_dir())
        if quest.is_file() and e4_dirs:
            out.append((sid, e4_dirs[0], quest))
    return out


def main() -> None:
    args = parse_args()
    if args.synthetic:
        rows = synthetic_training_rows(subjects=args.subjects)
        n = write_windows_csv(args.out, rows)
        print(f"wrote {n} synthetic windows -> {args.out}")
        return

    pickles = discover_pickles(args.wesad_root)
    rows: list = []
    if pickles:
        for path in pickles:
            subject = path.stem
            part = windows_from_wesad_subject(path, subject_id=subject)
            print(f"{subject}: {len(part)} windows from {path}")
            rows.extend(part)
        n = write_windows_csv(args.out, rows)
        print(f"wrote {n} windows from {len(pickles)} pickles -> {args.out}")
        return

    e4 = discover_e4_subjects(args.wesad_root)
    if not e4:
        raise SystemExit(
            f"no WESAD pickles or E4 BVP+quest under {args.wesad_root}. "
            "Download per docs/WESAD.md, or pass --synthetic for a smoke CSV."
        )
    for sid, e4_dir, quest_path in e4:
        part = windows_from_wesad_e4(e4_dir, quest_path, subject_id=sid)
        print(f"{sid}: {len(part)} windows from {e4_dir}")
        rows.extend(part)
    n = write_windows_csv(args.out, rows)
    print(f"wrote {n} windows from {len(e4)} E4 subjects -> {args.out}")


if __name__ == "__main__":
    main()
