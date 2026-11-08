"""Pretend to be the watch app: find the Pi's RR service, connect, write a packet every second.

Tests the Pi receiver over real Bluetooth before the Connect IQ app exists. Run it on any machine
with Bluetooth (e.g. the Windows PC) while the Pi runs `python -m dms_physiology.garmin_receiver`.

    python tools/fake_watch.py --seconds 60
    python tools/fake_watch.py --drop-every 10 --dup-every 7 --restart-at 30

Beats: heart rate around --hr bpm with a slow breathing swing (+-4 bpm, 0.25 Hz) and 15 ms of
random beat-to-beat noise, so the HRV stage later sees realistic numbers. Uses the shared codec,
so a passing run also checks that both sides agree on docs/packet_format.md.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dms_physiology.garmin_rr import (  # noqa: E402
    CHARACTERISTIC_UUID,
    MAX_RR_PER_PACKET,
    SERVICE_UUID,
    RrFlags,
    RrPacket,
    encode,
)


class BeatGenerator:
    """Synthetic RR intervals: mean HR + respiratory sinus arrhythmia + noise."""

    def __init__(self, hr: float, seed: int = 0) -> None:
        self.hr, self.t, self.rng = hr, 0.0, random.Random(seed)

    def next_second(self) -> list[int]:
        out, end = [], math.floor(self.t) + 1.0
        while self.t < end:
            bpm = self.hr + 4.0 * math.sin(2 * math.pi * 0.25 * self.t)
            rr = 60000.0 / bpm + self.rng.gauss(0.0, 15.0)
            self.t += rr / 1000.0
            out.append(int(round(rr)))
        return out


async def run(args: argparse.Namespace) -> None:
    from bleak import BleakClient, BleakScanner

    print(f"scanning for the RR service {SERVICE_UUID} ...", flush=True)
    dev = await BleakScanner.find_device_by_filter(
        lambda d, adv: SERVICE_UUID in [u.lower() for u in adv.service_uuids], timeout=20.0)
    if dev is None:
        raise SystemExit("Pi not found - is garmin_receiver running and Bluetooth on?")
    print(f"found {dev.name} [{dev.address}]", flush=True)
    beats = BeatGenerator(args.hr, args.seed)
    seq, t0 = 0, time.monotonic()
    sent = dropped = dups = 0
    async with BleakClient(dev) as client:
        watch_ms = 1_000_000  # the watch uptime clock never starts at 0
        for second in range(int(args.seconds)):
            if args.restart_at and second == args.restart_at:
                print("-- simulating an app restart (seq back to 0)", flush=True)
                seq = 0
            rr = beats.next_second()
            chunks = [rr[i:i + MAX_RR_PER_PACKET] for i in range(0, len(rr), MAX_RR_PER_PACKET)]
            for k, chunk in enumerate(chunks):
                flags = RrFlags.SPLIT if k < len(chunks) - 1 else RrFlags.NONE
                hr = int(round(60000 / (sum(chunk) / len(chunk))))
                raw = encode(RrPacket(seq=seq % 65536, watch_ms=watch_ms, hr_bpm=hr,
                                      rr_ms=tuple(chunk), flags=flags))
                if args.drop_every and seq and seq % args.drop_every == 0:
                    dropped += 1  # pretend the radio lost it
                else:
                    await client.write_gatt_char(CHARACTERISTIC_UUID, raw, response=False)
                    sent += 1
                    if args.dup_every and seq and seq % args.dup_every == 0:
                        await client.write_gatt_char(CHARACTERISTIC_UUID, raw, response=False)
                        dups += 1
                print(f"seq {seq:5d} hr {hr:3d} rr {chunk}", flush=True)
                seq += 1
            watch_ms += 1000
            await asyncio.sleep(max(0.0, t0 + second + 1 - time.monotonic()))
    print(f"sent {sent}, deliberately dropped {dropped}, duplicated {dups}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--hr", type=float, default=72.0, help="mean heart rate, bpm")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--drop-every", type=int, default=0, help="skip every Nth packet (loss test)")
    p.add_argument("--dup-every", type=int, default=0, help="send every Nth packet twice")
    p.add_argument("--restart-at", type=int, default=0, help="reset seq to 0 at this second")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
