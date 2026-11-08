"""Step 1 of the Garmin plan: does the watch's built-in "Broadcast Heart Rate" carry RR intervals?

The watch broadcasts the standard Bluetooth Heart Rate Service (0x180D). Every notification on
the Heart Rate Measurement characteristic (0x2A37) starts with a flags byte; bit 4 says whether
RR intervals are included. HRV needs RR intervals, so this script connects, listens, prints what
arrives once per second, and ends with a one-line verdict.

On the watch: hold UP (Menu) > Settings > Sensors & Accessories > Wrist Heart Rate >
Broadcast Heart Rate (or the "Broadcast HR" control). Leave it broadcasting while this runs.

    python tools/check_garmin_broadcast.py                  # find the watch by service, 120 s
    python tools/check_garmin_broadcast.py --name Forerunner --seconds 60

Runs anywhere bleak runs (Raspberry Pi OS / Linux with BlueZ, Windows, macOS). Only needs bleak.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field

HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"

# Heart Rate Measurement flags (Bluetooth Heart Rate Profile).
FLAG_HR_UINT16 = 0x01  # bit 0: heart rate is 2 bytes instead of 1
FLAG_CONTACT_SUPPORTED = 0x04  # bit 2: sensor contact detection is supported
FLAG_CONTACT_DETECTED = 0x02  # bit 1: skin contact detected (valid only if bit 2 set)
FLAG_ENERGY = 0x08  # bit 3: 2-byte energy expended field present
FLAG_RR = 0x10  # bit 4: one or more 2-byte RR intervals follow


@dataclass
class HrMeasurement:
    """One decoded Heart Rate Measurement notification."""

    flags: int
    heart_rate_bpm: int
    rr_ms: list[float]
    energy_kj: int | None = None


def parse_hr_measurement(data: bytes) -> HrMeasurement:
    """Decode a Heart Rate Measurement (0x2A37) value.

    Layout: flags (1 byte), heart rate (1 or 2 bytes), energy expended (2 bytes, optional),
    then RR intervals (2 bytes each, little-endian, in units of 1/1024 s) until the end.
    """
    if len(data) < 2:
        raise ValueError(f"too short: {len(data)} bytes")
    flags = data[0]
    i = 1
    if flags & FLAG_HR_UINT16:
        if len(data) < 3:
            raise ValueError("16-bit heart rate flag set but value missing")
        hr = int.from_bytes(data[1:3], "little")
        i = 3
    else:
        hr = data[1]
        i = 2
    energy = None
    if flags & FLAG_ENERGY:
        if len(data) < i + 2:
            raise ValueError("energy flag set but value missing")
        energy = int.from_bytes(data[i:i + 2], "little")
        i += 2
    rr: list[float] = []
    if flags & FLAG_RR:
        if (len(data) - i) % 2:
            raise ValueError("RR flag set but an odd number of RR bytes follows")
        for j in range(i, len(data), 2):
            raw = int.from_bytes(data[j:j + 2], "little")
            rr.append(raw * 1000.0 / 1024.0)  # 1/1024 s -> ms
    return HrMeasurement(flags, hr, rr, energy)


@dataclass
class Tally:
    """Counts over the whole run, for the verdict."""

    notifications: int = 0
    with_rr_flag: int = 0
    rr_values: int = 0
    errors: int = 0
    second: list[tuple[int, HrMeasurement]] = field(default_factory=list)  # this second's data


def describe_flags(flags: int) -> str:
    parts = [f"0x{flags:02X}", f"0b{flags:08b}"]
    parts.append("hr16" if flags & FLAG_HR_UINT16 else "hr8")
    if flags & FLAG_CONTACT_SUPPORTED:
        parts.append("contact" if flags & FLAG_CONTACT_DETECTED else "NO-contact")
    if flags & FLAG_ENERGY:
        parts.append("energy")
    parts.append("RR" if flags & FLAG_RR else "no-RR")
    return " ".join(parts)


async def find_watch(name: str | None, timeout: float) -> object | None:
    """Scan for a device advertising the Heart Rate Service (and matching `name`, if given)."""
    from bleak import BleakScanner

    def match(device: object, adv: object) -> bool:
        uuids = [u.lower() for u in getattr(adv, "service_uuids", []) or []]
        dev_name = (getattr(adv, "local_name", None) or getattr(device, "name", None) or "")
        if name:
            return name.lower() in dev_name.lower()
        return HR_SERVICE in uuids

    print(f"scanning up to {timeout:.0f} s for "
          f"{'a device named *' + name + '*' if name else 'a heart-rate broadcast (0x180D)'} ...")
    return await BleakScanner.find_device_by_filter(match, timeout=timeout)


async def run(args: argparse.Namespace) -> int:
    from bleak import BleakClient

    tally = Tally()
    t_start = time.monotonic()
    t_end = t_start + args.seconds

    def on_notify(_sender: object, data: bytearray) -> None:
        try:
            m = parse_hr_measurement(bytes(data))
        except ValueError as e:
            tally.errors += 1
            print(f"  bad packet {bytes(data).hex()}: {e}")
            return
        tally.notifications += 1
        if m.flags & FLAG_RR:
            tally.with_rr_flag += 1
            tally.rr_values += len(m.rr_ms)
        tally.second.append((len(data), m))

    while time.monotonic() < t_end:
        device = await find_watch(args.name, timeout=min(20.0, t_end - time.monotonic()))
        if device is None:
            print("  not found - is Broadcast Heart Rate on, and the watch close by?")
            continue
        print(f"found {getattr(device, 'name', None) or '?'} [{getattr(device, 'address', '?')}]")
        try:
            async with BleakClient(device) as client:
                await client.start_notify(HR_MEASUREMENT, on_notify)
                print(f"listening for {t_end - time.monotonic():.0f} s "
                      "(one line per second: t, notifications, flags, HR, RR in ms)")
                next_print = time.monotonic() + 1.0
                while client.is_connected and time.monotonic() < t_end:
                    await asyncio.sleep(max(0.0, next_print - time.monotonic()))
                    next_print += 1.0
                    batch, tally.second = tally.second, []
                    t = time.monotonic() - t_start
                    if not batch:
                        print(f"{t:6.1f}s  0 notifications")
                        continue
                    flags = " | ".join(sorted({describe_flags(m.flags) for _, m in batch}))
                    hrs = ",".join(str(m.heart_rate_bpm) for _, m in batch)
                    rrs = [f"{r:.0f}" for _, m in batch for r in m.rr_ms]
                    print(f"{t:6.1f}s  {len(batch)} notif  flags {flags}  HR {hrs}  "
                          f"RR {' '.join(rrs) if rrs else '-'}")
                if not client.is_connected:
                    print("  disconnected - scanning again")
        except Exception as e:  # noqa: BLE001 - report and retry until time is up
            print(f"  connection error: {e!r} - retrying")
            await asyncio.sleep(2.0)

    print()
    print(f"notifications: {tally.notifications}, with RR flag: {tally.with_rr_flag}, "
          f"RR values: {tally.rr_values}, bad packets: {tally.errors}")
    if tally.notifications == 0:
        print("RR present: unknown (no heart-rate data received)")
        return 2
    present = tally.rr_values > 0
    print(f"RR present: {'yes' if present else 'no'}")
    return 0 if present else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seconds", type=float, default=120.0, help="how long to listen (default 120)")
    p.add_argument("--name", help="match the watch by (part of) its name instead of by service")
    return asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
