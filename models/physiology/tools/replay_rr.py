"""Replay RR data through the HRV stage without the watch: a recorded receiver log, or synthetic.

    python tools/replay_rr.py logs/garmin_rr_20261011_221839.csv     # recorded session
    python tools/replay_rr.py --synthetic 300 --artifacts 0.03 --loss 0.02
    python tools/replay_rr.py rr.csv --out hrv.csv                    # also save every update

Recorded: rows of the receiver's raw CSV (garmin_receiver.RrCsvLog) are turned back into frames
with their original Pi timestamps; duplicates / late / undecodable rows are skipped, as live.
Synthetic: a heart at --hr bpm with breathing swing and beat noise, packed one packet per
second like the watch, optional artifact beats and lost packets, through the real
SequenceTracker. Either way RrHrv computes a 60 s window every 5 s, exactly as the service does.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dms_physiology.garmin_hrv import UPDATE_S, RrHrv  # noqa: E402
from dms_physiology.garmin_rr import (  # noqa: E402
    Arrival,
    RrFlags,
    RrFrame,
    RrPacket,
    SequenceTracker,
)


def frames_from_log(path: Path) -> Iterator[RrFrame]:
    for row in csv.DictReader(path.open(encoding="utf8")):
        if row["arrival"] not in ("new", "new_session"):
            continue
        rr = tuple(int(x) for x in row["rr_ms"].split()) if row["rr_ms"] else ()
        hr = int(row["hr_bpm"]) if row["hr_bpm"] else None
        packet = RrPacket(seq=int(row["seq"]), watch_ms=int(row["watch_ms"]), hr_bpm=hr,
                          rr_ms=rr, flags=RrFlags.HR_VALID if hr else RrFlags.NONE)
        yield RrFrame(packet, float(row["rx_monotonic"]), float(row["rx_wall"]),
                      Arrival(row["arrival"]), int(row["lost_before"]),
                      bool(int(row["gap_before"])), int(row["session"]))


def synthetic_frames(seconds: float, hr: float, artifacts: float, loss: float,
                     seed: int) -> Iterator[RrFrame]:
    rng = random.Random(seed)
    tracker = SequenceTracker()
    t, beat_t, seq, watch_ms = 1000.0, 0.0, 0, 1_000_000
    pending: list[int] = []
    while t < 1000.0 + seconds:
        # beats until the next 1 s packet boundary
        while beat_t < t - 1000.0 + 1.0:
            bpm = hr + 4.0 * math.sin(2 * math.pi * 0.25 * beat_t)
            rr = 60000.0 / bpm + rng.gauss(0.0, 15.0)
            if rng.random() < artifacts:
                rr *= rng.choice((0.5, 1.9))  # extra / missed beat
            beat_t += rr / 1000.0
            pending.append(int(round(rr)))
        t += 1.0
        watch_ms += 1000
        packet = RrPacket(seq=seq % 65536, watch_ms=watch_ms, hr_bpm=int(hr),
                          rr_ms=tuple(pending[:5]))
        pending, seq = pending[5:], seq + 1
        if rng.random() < loss:
            continue
        frame = tracker.accept(packet, t, 1.8e9 + t)
        if frame.arrival in (Arrival.NEW, Arrival.NEW_SESSION):
            yield frame


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("log", nargs="?", help="receiver CSV (omit with --synthetic)")
    p.add_argument("--synthetic", type=float, metavar="SECONDS", help="generate this many seconds")
    p.add_argument("--hr", type=float, default=70.0)
    p.add_argument("--artifacts", type=float, default=0.0, help="fraction of bad beats")
    p.add_argument("--loss", type=float, default=0.0, help="fraction of lost packets")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", help="write every update to this CSV")
    a = p.parse_args()
    if a.synthetic:
        frames = list(synthetic_frames(a.synthetic, a.hr, a.artifacts, a.loss, a.seed))
    elif a.log:
        frames = list(frames_from_log(Path(a.log)))
    else:
        p.error("give a receiver CSV or --synthetic SECONDS")
    if not frames:
        raise SystemExit("no frames")
    hrv = RrHrv()
    rows = []
    next_update = frames[0].rx_monotonic + UPDATE_S
    for f in frames:
        while f.rx_monotonic >= next_update:  # the service's 5 s timer
            rows.append(hrv.compute(next_update).to_dict())
            next_update += UPDATE_S
        hrv.add(f)
    rows.append(hrv.compute(frames[-1].rx_monotonic).to_dict())
    print(f"{len(frames)} packets, {rows[-1]['t_monotonic'] - frames[0].rx_monotonic:.0f} s")
    print(f"{'t':>6} {'state':9} {'HR':>5} {'RMSSD':>6} {'SDNN':>6} {'pNN50':>6} "
          f"{'qual':9} {'loss':>5} {'artif':>5} {'cover':>5} {'beats':>5}")
    t0 = frames[0].rx_monotonic
    for r in rows:
        def fmt(v: object, w: int) -> str:
            return f"{'-':>{w}}" if v is None else f"{v:>{w}}"
        print(f"{float(r['t_monotonic']) - t0:6.0f} {r['state']:9} {fmt(r['mean_hr_bpm'], 5)} "
              f"{fmt(r['rmssd_ms'], 6)} {fmt(r['sdnn_ms'], 6)} {fmt(r['pnn50'], 6)} "
              f"{r['quality']:9} {r['packet_loss']:>5} {r['artifacts']:>5} {r['coverage']:>5} "
              f"{r['valid_beats']:>5}")
    if a.out:
        with open(a.out, "w", newline="", encoding="utf8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"written {a.out}")


if __name__ == "__main__":
    main()
