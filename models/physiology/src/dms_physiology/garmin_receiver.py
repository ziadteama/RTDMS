"""Pi-side Bluetooth receiver for the Garmin RR stream (docs/packet_format.md).

The Pi is the BLE peripheral: it advertises one GATT service with one writable characteristic.
The watch app (central) finds the service, connects, and writes one packet per ~1 s. Each write:

    bytes -> decode (garmin_rr) -> stamp with Pi time -> SequenceTracker -> CSV row
          -> queue for the HRV stage (only NEW / NEW_SESSION frames)

Reconnection needs nothing from this side: the Pi keeps advertising, and when the watch comes
back it connects again; a restarted app shows up as a NEW_SESSION. Liveness is judged from data,
not from connection events: `seconds_since_last_packet()` grows when the watch is gone.

    python -m dms_physiology.garmin_receiver                  # log to logs/garmin_rr_<time>.csv
    python -m dms_physiology.garmin_receiver --csv rr.csv --name RTDMS

Linux / BlueZ (Raspberry Pi OS Bookworm) with the optional dependency: pip install ".[garmin]".
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import logging
import os
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, TextIO

from .garmin_hrv import UPDATE_S, RrHrv
from .garmin_live import LiveState, serve
from .garmin_rr import (
    CHARACTERISTIC_UUID,
    SERVICE_UUID,
    Arrival,
    RrCodecError,
    RrFrame,
    SequenceTracker,
    decode,
)

LOG = logging.getLogger("garmin_receiver")
CSV_FIELDS = ["rx_wall", "rx_monotonic", "arrival", "session", "seq", "watch_ms", "hr_bpm",
              "rr_ms", "lost_before", "gap_before", "raw_hex"]


class RrCsvLog:
    """One CSV row per received write, including duplicates and undecodable bytes (raw data)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        self._file: TextIO = path.open("a", newline="", encoding="utf8")
        self._csv = csv.writer(self._file)
        if new:
            self._csv.writerow(CSV_FIELDS)
        self.path = path

    def frame(self, f: RrFrame, raw: bytes) -> None:
        p = f.packet
        self._csv.writerow([f"{f.rx_wall:.3f}", f"{f.rx_monotonic:.3f}", f.arrival.value,
                            f.session, p.seq, p.watch_ms, "" if p.hr_bpm is None else p.hr_bpm,
                            " ".join(str(r) for r in p.rr_ms), f.lost_before,
                            int(f.gap_before), raw.hex()])
        self._file.flush()  # ~1 row per second: flush so a power cut loses at most one row

    def bad(self, rx_monotonic: float, rx_wall: float, raw: bytes, why: str) -> None:
        self._csv.writerow([f"{rx_wall:.3f}", f"{rx_monotonic:.3f}", f"bad: {why}", "", "", "",
                            "", "", "", "", raw.hex()])
        self._file.flush()

    def close(self) -> None:
        self._file.close()


class GarminRrReceiver:
    """Decodes watch writes and hands accepted frames to the HRV stage.

    `handle_write` is the whole receive path and has no Bluetooth in it, so the tests and the
    simulator drive it directly. `run` adds the BLE peripheral around it.
    """

    def __init__(self, log: RrCsvLog | None = None, max_queue: int = 256,
                 clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time) -> None:
        self.tracker = SequenceTracker()
        self.decode_errors = 0
        self.dropped_frames = 0  # queue full: the HRV stage fell behind (should stay 0)
        self._log = log
        self._clock, self._wall = clock, wall
        self._queue: asyncio.Queue[RrFrame] = asyncio.Queue(maxsize=max_queue)
        self._last_rx: float | None = None

    def handle_write(self, raw: bytes) -> RrFrame | None:
        """One BLE write from the watch. Returns the frame passed on, or None if dropped."""

        rx_mono, rx_wall = self._clock(), self._wall()
        try:
            packet = decode(raw)
        except RrCodecError as e:
            self.decode_errors += 1
            if self._log:
                self._log.bad(rx_mono, rx_wall, raw, str(e))
            return None
        frame = self.tracker.accept(packet, rx_mono, rx_wall)
        if self._log:
            self._log.frame(frame, raw)
        if frame.arrival in (Arrival.DUPLICATE, Arrival.LATE):
            return None
        self._last_rx = rx_mono
        if self._queue.full():
            self.dropped_frames += 1
        else:
            self._queue.put_nowait(frame)
        return frame

    def seconds_since_last_packet(self) -> float | None:
        return None if self._last_rx is None else self._clock() - self._last_rx

    async def frames(self) -> AsyncIterator[RrFrame]:
        """Accepted frames in arrival order, for the HRV stage."""
        while True:
            yield await self._queue.get()

    async def run(self, name: str = "RTDMS", stop: asyncio.Event | None = None) -> None:
        """Advertise the RR service and receive until `stop` is set (or forever).

        Linux (the Pi): BlueZ through bless. Windows (a PC standing in for the Pi): the
        Windows GATT server API, which bleak's winrt dependencies already provide."""

        if os.name == "nt":  # Windows (os.name keeps mypy checking both branches)
            await self._run_windows(stop)
            return
        from bless import (
            BlessServer,
            GATTAttributePermissions,
            GATTCharacteristicProperties,
        )

        loop = asyncio.get_running_loop()
        server = BlessServer(name=name, loop=loop)

        def on_write(_characteristic: Any, value: Any, **_: Any) -> None:
            # Called from BlueZ's D-Bus handler on this event loop; keep it short.
            self.handle_write(bytes(value))

        server.write_request_func = on_write
        server.read_request_func = lambda *_a, **_k: bytearray()
        props = GATTCharacteristicProperties
        # One service only: bless 0.2.6 advertised the first service and dropped a second one
        # from the GATT table (seen 2026-11-08), and the watch needs the advertised 16-bit UUID.
        await server.add_new_service(SERVICE_UUID)
        await server.add_new_characteristic(
            SERVICE_UUID, CHARACTERISTIC_UUID, props.write | props.write_without_response,
            None, GATTAttributePermissions.writeable)
        await server.start()
        LOG.info("advertising RR service %s as %r; waiting for the watch", SERVICE_UUID[4:8], name)
        try:
            await (stop or asyncio.Event()).wait()
        finally:
            await server.stop()

    async def _run_windows(self, stop: asyncio.Event | None) -> None:
        """Same service on Windows: GattServiceProvider + one writable characteristic.

        Windows advertises under the PC's own Bluetooth name; the watch finds the service by
        its UUID, which is in the advertisement."""

        import importlib
        import uuid

        # Loaded by name: the winrt type stubs need a newer Python than mypy checks against.
        gatt: Any = importlib.import_module(
            "winrt.windows.devices.bluetooth.genericattributeprofile")
        GattCharacteristicProperties = gatt.GattCharacteristicProperties  # noqa: N806
        GattLocalCharacteristicParameters = gatt.GattLocalCharacteristicParameters  # noqa: N806
        GattProtectionLevel = gatt.GattProtectionLevel  # noqa: N806
        GattServiceProvider = gatt.GattServiceProvider  # noqa: N806
        GattServiceProviderAdvertisingParameters = (  # noqa: N806
            gatt.GattServiceProviderAdvertisingParameters)
        GattWriteOption = gatt.GattWriteOption  # noqa: N806

        loop = asyncio.get_running_loop()
        made = await GattServiceProvider.create_async(uuid.UUID(SERVICE_UUID))
        provider = made.service_provider
        if provider is None:
            raise RuntimeError(f"Windows refused the GATT service (error {made.error})")
        params = GattLocalCharacteristicParameters()
        params.characteristic_properties = (GattCharacteristicProperties.WRITE
                                            | GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE)
        params.write_protection_level = GattProtectionLevel.PLAIN
        made_char = await provider.service.create_characteristic_async(
            uuid.UUID(CHARACTERISTIC_UUID), params)
        char = made_char.characteristic
        if char is None:
            raise RuntimeError(f"Windows refused the characteristic (error {made_char.error})")

        async def take(args: Any) -> None:
            deferral = args.get_deferral()
            try:
                request = await args.get_request_async()
                self.handle_write(bytes(request.value))
                if request.option == GattWriteOption.WRITE_WITH_RESPONSE:
                    request.respond()
            finally:
                deferral.complete()

        def on_write(_sender: Any, args: Any) -> None:
            # Raised on a Windows thread pool thread: hand over to the asyncio loop.
            asyncio.run_coroutine_threadsafe(take(args), loop)

        token = char.add_write_requested(on_write)
        adv = GattServiceProviderAdvertisingParameters()
        adv.is_connectable = True
        adv.is_discoverable = True
        provider.start_advertising(adv)
        # Windows reports success from start_advertising() even when the advertisement is then
        # aborted (seen on a Realtek RTL8852CE laptop), so wait for it to really be STARTED.
        started = 2  # GattServiceProviderAdvertisementStatus.STARTED
        for _ in range(30):
            if int(provider.advertisement_status) == started:
                break
            await asyncio.sleep(0.1)
        else:
            char.remove_write_requested(token)
            raise RuntimeError(
                f"Windows did not start advertising (status {int(provider.advertisement_status)}"
                ", 3 = aborted). This PC's Bluetooth cannot act as the receiver; use the Pi.")
        LOG.info("advertising %s (Windows); waiting for the watch", SERVICE_UUID)
        try:
            await (stop or asyncio.Event()).wait()
        finally:
            provider.stop_advertising()
            char.remove_write_requested(token)


async def _main(args: argparse.Namespace) -> None:
    path = Path(args.csv or f"logs/garmin_rr_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    log = RrCsvLog(path)
    rx = GarminRrReceiver(log)
    hrv = RrHrv()
    live = LiveState(rx.tracker)
    print(f"[garmin] logging to {path}", flush=True)
    if args.http:
        serve(live, args.http)
        print(f"[garmin] live page on http://<this machine>:{args.http}/", flush=True)

    async def show() -> None:
        async for f in rx.frames():
            hrv.add(f)
            live.on_frame(f)
            live.decode_errors = rx.decode_errors
            if args.quiet:
                continue
            p = f.packet
            note = " NEW SESSION" if f.arrival == Arrival.NEW_SESSION else ""
            note += f" lost {f.lost_before}" if f.lost_before else ""
            print(f"[garmin] seq {p.seq:5d} hr {p.hr_bpm or '--':>3} rr {list(p.rr_ms)}{note}",
                  flush=True)

    async def hrv_timer() -> None:
        # The HRV window is computed on the Pi clock every UPDATE_S, whether or not beats came.
        while True:
            await asyncio.sleep(UPDATE_S)
            snap = hrv.compute(time.monotonic(), time.time())
            live.on_hrv(snap)
            d = snap.to_dict()
            print(f"[hrv] {d['state']:8} HR {d['mean_hr_bpm']} RMSSD {d['rmssd_ms']} "
                  f"SDNN {d['sdnn_ms']} pNN50 {d['pnn50']} | quality {d['quality']} "
                  f"beats {d['valid_beats']} coverage {d['coverage']} loss {d['packet_loss']}",
                  flush=True)

    async def stale() -> None:
        warned = False
        while True:
            await asyncio.sleep(1.0)
            age = rx.seconds_since_last_packet()
            if age is not None and age > args.stale_s and not warned:
                print(f"[garmin] no data for {age:.0f} s (watch away / app closed)", flush=True)
            warned = age is not None and age > args.stale_s

    tasks = [asyncio.create_task(show()), asyncio.create_task(stale()),
             asyncio.create_task(hrv_timer())]
    try:
        await rx.run(args.name)
    finally:
        for t in tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        log.close()
        t_ = rx.tracker
        print(f"[garmin] received {t_.received}, lost {t_.lost}, duplicates {t_.duplicates}, "
              f"late {t_.late}, decode errors {rx.decode_errors}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--csv", help="raw log file (default logs/garmin_rr_<time>.csv)")
    p.add_argument("--name", default="RTDMS", help="advertised Bluetooth name")
    p.add_argument("--stale-s", type=float, default=5.0, help="warn after this long without data")
    p.add_argument("--http", type=int, default=8081,
                   help="port of the live page + /status JSON (0 = off)")
    p.add_argument("--quiet", action="store_true", help="no line per packet (HRV lines only)")
    logging.basicConfig(level=logging.INFO, format="[garmin] %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main(p.parse_args()))


if __name__ == "__main__":
    main()
