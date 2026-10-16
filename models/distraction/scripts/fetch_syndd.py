#!/usr/bin/env python3
"""Fetch SynDD (AI City 2024 Track 3) A1 rear-view videos + annotation CSVs from Google Drive
WITHOUT downloading the 40 GB zips: the zip index is read through byte-range requests
(`rclone cat --offset --count`) and only the wanted members are streamed out.

    python scripts/fetch_syndd.py --list                       # zips and their members
    python scripts/fetch_syndd.py --users 1                    # first user only (layout check)
    python scripts/fetch_syndd.py                              # every A1 user

Needs an rclone remote with read access to the folder (default: gdrive, read-only scope).
Output: <data root>/public/syndd/A1/user_id_XXXXX/{user_id_XXXXX.csv, Rearview_*.MP4}.
Dashboard and right-side-window videos and A2 (no annotations) are never read.
Existing files with the right size are skipped, so the script can be rerun after a break.
"""

from __future__ import annotations

import argparse
import io
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FOLDER_ID = "1SZkaq6Coec14G7w-WFUYr-iH7Z5GVtRQ"
LABELS_ZIP = "2024-data_labelsAndinstructions.zip"
USER = re.compile(r"user_id_(\d+)", re.I)


class Remote:
    def __init__(self, rclone: str, remote: str, folder_id: str):
        self.rclone, self.remote, self.folder = rclone, remote, folder_id

    def _base(self, *a):
        return [self.rclone, *a, "--drive-root-folder-id", self.folder, "-q"]

    def sizes(self) -> dict[str, int]:
        out = subprocess.run(self._base("lsf", f"{self.remote}:", "--format", "ps",
                                        "--separator", "|"),
                             capture_output=True, text=True, check=True).stdout
        return {n: int(s) for n, s in (ln.rsplit("|", 1) for ln in out.splitlines() if ln)}

    def cat(self, name: str, offset: int, count: int) -> bytes:
        return subprocess.run(self._base("cat", f"{self.remote}:{name}", "--offset", str(offset),
                                         "--count", str(count)),
                              capture_output=True, check=True).stdout

    def stream(self, name: str, offset: int, count: int):
        return subprocess.Popen(self._base("cat", f"{self.remote}:{name}", "--offset",
                                           str(offset), "--count", str(count)),
                                stdout=subprocess.PIPE, bufsize=1 << 20)


class RangeFile(io.RawIOBase):
    """Seekable read-only view of a remote file; 4 MB aligned blocks, LRU of 8."""

    BLOCK = 4 << 20

    def __init__(self, remote: Remote, name: str, size: int):
        self.r, self.name, self.size, self.pos, self.cache = remote, name, size, 0, {}

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def _block(self, i):
        if i not in self.cache:
            if len(self.cache) >= 8:
                self.cache.pop(next(iter(self.cache)))
            start = i * self.BLOCK
            self.cache[i] = self.r.cat(self.name, start, min(self.BLOCK, self.size - start))
        return self.cache[i]

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        out = bytearray()
        while n > 0 and self.pos < self.size:
            b = self._block(self.pos // self.BLOCK)
            k = self.pos % self.BLOCK
            chunk = b[k:k + n]
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)


def extract_member(remote: Remote, zname: str, info: zipfile.ZipInfo, dest: Path) -> str:
    if dest.is_file() and dest.stat().st_size == info.file_size:
        return f"have {dest.name}"
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or info.flag_bits & 1:
        raise SystemExit(f"{info.filename}: unsupported compression / encryption")
    hdr = remote.cat(zname, info.header_offset, 30)  # local header: name / extra lengths
    if hdr[:4] != b"PK\x03\x04":
        raise RuntimeError(f"{info.filename}: no local header at {info.header_offset}")
    n_name, n_extra = struct.unpack("<HH", hdr[26:30])
    data = info.header_offset + 30 + n_name + n_extra
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    dec = zlib.decompressobj(-15) if info.compress_type == zipfile.ZIP_DEFLATED else None
    crc, size = 0, 0
    p = remote.stream(zname, data, info.compress_size)
    with open(tmp, "wb") as f:
        while chunk := p.stdout.read(8 << 20):
            if dec:
                chunk = dec.decompress(chunk)
            crc, size = zlib.crc32(chunk, crc), size + len(chunk)
            f.write(chunk)
        if dec:
            tail = dec.flush()
            crc, size = zlib.crc32(tail, crc), size + len(tail)
            f.write(tail)
    if p.wait() != 0 or size != info.file_size or crc != info.CRC:
        raise RuntimeError(f"{info.filename}: transfer check failed (size {size}/"
                           f"{info.file_size}, crc ok {crc == info.CRC})")
    tmp.replace(dest)
    return f"got  {dest.name} ({size / 1e9:.2f} GB)"


def extract_retry(remote: Remote, zname: str, info: zipfile.ZipInfo, dest: Path,
                  tries: int = 8) -> str:
    """Network drops (DNS / connection resets) fail a transfer's size / CRC check; retry the
    member from the start with a growing wait (30 s, 60 s, ... up to 5 min)."""
    for k in range(1, tries + 1):
        try:
            return extract_member(remote, zname, info, dest)
        except (RuntimeError, subprocess.CalledProcessError, OSError) as e:
            if k == tries:
                raise
            wait = min(300, 30 * k)
            print(f"   retry {k}/{tries - 1} in {wait} s: {e}", flush=True)
            time.sleep(wait)
    raise AssertionError("unreachable")


def wanted(name: str) -> bool:
    base = Path(name).name
    return (not name.startswith("__MACOSX") and USER.search(name) is not None and
            (base.lower().endswith(".csv") or
             (base.lower().startswith("rear") and base.lower().endswith(".mp4"))))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--rclone", default=shutil.which("rclone") or "rclone")
    p.add_argument("--remote", default="gdrive")
    p.add_argument("--folder-id", default=FOLDER_ID)
    p.add_argument("--users", type=int, help="stop after this many users (layout check)")
    p.add_argument("--jobs", type=int, default=3, help="parallel member transfers")
    p.add_argument("--list", action="store_true")
    args = p.parse_args()

    root = Path(yaml.safe_load((ROOT / "configs" / "data.yaml").read_text(encoding="utf8"))
                ["root"]) / "public" / "syndd"
    out = root / "A1"
    remote = Remote(args.rclone, args.remote, args.folder_id)
    sizes = remote.sizes()
    zips = sorted(n for n in sizes if re.fullmatch(r"A1_\d+\.zip", n))
    if not zips:
        raise SystemExit(f"no A1_*.zip in the folder (found: {sorted(sizes)})")

    # official annotation CSVs (labels zip -> nested A1.zip)
    lab = zipfile.ZipFile(io.BytesIO(remote.cat(LABELS_ZIP, 0, sizes[LABELS_ZIP])))
    inner = zipfile.ZipFile(io.BytesIO(lab.read("labels&instructions/A1.zip")))
    # keyed by the user id in the rows: user_id_79775.csv annotates user_id_79755's videos
    csvs = {}
    for n in inner.namelist():
        if n.endswith(".csv") and not n.startswith("__MACOSX") and USER.search(n):
            m = USER.search(inner.read(n).decode("utf-8-sig").split("\n", 2)[1])
            csvs[m.group(1) if m else USER.search(n).group(1)] = n

    done_users: list[str] = []
    for zname in zips:
        for k in range(8):  # the zip index is a few range reads; retry them on a network drop
            try:
                zf = zipfile.ZipFile(RangeFile(remote, zname, sizes[zname]))
                break
            except subprocess.CalledProcessError:
                time.sleep(min(300, 30 * (k + 1)))
        else:
            raise SystemExit(f"{zname}: index unreadable after retries")
        members = [i for i in zf.infolist() if wanted(i.filename)]
        users = sorted({USER.search(i.filename).group(1) for i in members})
        print(f"{zname}: {len(zf.infolist())} entries, {len(users)} users, "
              f"{sum(i.file_size for i in members) / 1e9:.1f} GB rear-view + csv", flush=True)
        if args.list:
            for i in members[:12]:
                print(f"   {i.file_size / 1e9:6.2f} GB  {i.filename}")
            continue
        if args.users is not None:
            users = users[: max(0, args.users - len(done_users))]
        for uid in users:
            udir = out / f"user_id_{uid}"
            udir.mkdir(parents=True, exist_ok=True)
            if uid in csvs:
                (udir / f"user_id_{uid}.csv").write_bytes(inner.read(csvs[uid]))
            mine = [i for i in members if USER.search(i.filename).group(1) == uid and
                    i.filename.lower().endswith(".mp4")]
            with ThreadPoolExecutor(args.jobs) as ex:
                for msg in ex.map(lambda i, u=udir, z=zname: extract_retry(
                        remote, z, i, u / Path(i.filename).name), mine):
                    print(f"   user_id_{uid}: {msg}", flush=True)
            done_users.append(uid)
        if args.users is not None and len(done_users) >= args.users:
            break
    print(f"-> {out} ({len(done_users)} users)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
