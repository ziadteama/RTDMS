---
title: "Raspberry Pi 5 — Target Device"
tags:
  - subsystem
  - hardware
  - target-device
  - raspberry-pi
aliases:
  - raspberrypi
  - the Pi
  - target device
status: camera-attached
code_path: (deployment target)
language: Debian 13 trixie / arm64
surveyed: 2026-10-10
---

# Raspberry Pi 5 — Target Device

↑ [[Home]] | [[Models Index]] | Setup plan: [[Pi Setup Plan]]

The physical machine everything deploys to. First surveyed **2026-08-28**; re-checked over SSH on
**2026-09-20** (LAN `192.168.100.181` and Tailscale `100.113.107.122` both answered), and on
**2026-10-10** when the first camera went on and the face model ran live — see [[#Camera]].

> [!warning] Current state (2026-10-10): stand-in camera attached, face model running
> A third-party **OV5647 5 MP** camera (not the BOM's IR 160° module) is on the CSI port and the
> [[Face Subsystem]] runs live on it via `stream.py`. Still **no AI accelerator** and no wearable.
> See [[#Hardware gaps]] and [[#Camera]].

> [!important] Agent priority
> All agents must optimize for **this** box and the concurrent face + phone + physiology + fusion
> pipeline — see `.cursor/rules/pi-performance-pipeline.mdc`.

## Access

| | |
|---|---|
| Hostname | `raspberrypi` · `raspberrypi.tail5898c4.ts.net` |
| Tailscale IP | `100.113.107.122` (also `fd7a:115c:a1e0::8a01:6bc6`) |
| LAN IP | `192.168.100.181` (eth0, wired) |
| User | `khalifa` (uid 1000) |
| Groups | `sudo adm dialout video render gpio i2c spi input netdev` — already has what the project needs |

**Use the LAN IP with key auth:**

```bash
ssh -i ~/.ssh/id_ed25519 khalifa@192.168.100.181
```

> [!important] Why not the Tailscale IP
> Tailscale SSH intercepts port 22 on the tailnet address and this tailnet runs SSH in **check
> mode** — every connection demands an interactive browser re-auth
> (`login.tailscale.com/a/...`), which breaks non-interactive/automated use. The LAN IP reaches
> the Pi's real `sshd` and honours the existing SSH key. Only `khalifa` and `root` are permitted
> by the tailnet policy at all; `pi`, `ziad`, `admin`, `dms` are all denied.
>
> If remote (off-LAN) automation is ever needed, either relax `checkPeriod` in the tailnet ACL or
> disable Tailscale SSH for this node and rely on normal `sshd` over the tailnet.

Password auth also works but is **deliberately not recorded in this repo** — this vault is a git
repo that may be pushed to GitHub. Use the SSH key.

## Hardware

| Item | Value |
|---|---|
| Board | Raspberry Pi 5 Model B **Rev 1.1** |
| RAM | 8 GB (7.9 GiB usable) — matches [[4.5 Cost Calculation and BOM\|BOM]] |
| CPU | 4× Cortex-A76 @ 2.4 GHz (`arm_boost=1` already set) |
| Storage | **microSD** `mmcblk0` 58.2 GB — 57.7 GB root (30% used), 512 MB `/boot/firmware` |
| Swap | 2 GB zram |
| Bluetooth | BlueZ 5.82, `hci0` UART, `2C:CF:67:B6:26:3B`, active + enabled |
| Network | eth0 wired 192.168.100.181; wlan0 **down**; tailscale0 up |
| Bootloader | Up to date (2026-05-26) |
| Thermals | 48.3 °C idle (2026-09-20), `throttled=0x0` — healthy |
| Uptime at first survey | 39 min, load 0.07 (2026-08-28) |

## Software

| Item | Value |
|---|---|
| OS | **Debian 13 (trixie)** / Raspberry Pi OS, arm64 |
| Kernel | `6.18.39+rpt-rpi-2712` (2026-07-29) |
| Python | **3.13.5** (system) |
| Tailscale | 1.102.3 |
| Installed Python pkgs (system) | `numpy 2.2.4`, `picamera2 0.3.37` |
| Face venv `~/facemesh-venv` | `--system-site-packages` (keeps system numpy + picamera2) + `ai-edge-litert`, `onnxruntime 1.31.0`, `opencv-python-headless 5.0.0` — added 2026-10-10 |
| Converter venv `~/convert-venv` | `tflite2onnx`, `onnx 1.23.2` — offline tooling only, not on the runtime path |
| Not installed | scipy, mediapipe, bleak, ultralytics, hailo-platform, torch, Docker |
| CPU governor | `ondemand` (max 2.4 GHz) |
| Pending updates | openssl / libssl3t64 **security** updates, ffmpeg libs |

### Boot configuration

`/boot/firmware/config.txt` is stock **except the camera lines** (changed 2026-10-10, backup at
`config.txt.bak`). Relevant lines:

```
#dtparam=i2c_arm=on      <- COMMENTED OUT
#dtparam=spi=on          <- COMMENTED OUT
camera_auto_detect=0     <- was 1; the OV5647 clone is not auto-detected
display_auto_detect=1
dtoverlay=vc4-kms-v3d
arm_boost=1
[pi5]
dtoverlay=nospi10
[all]
# OV5647 camera
dtoverlay=ov5647         <- one overlay per CSI port, so either socket works
dtoverlay=ov5647,cam0
```

The empty port logs `ov5647 11-0036 ... probe failed with error -121` at every boot — expected, not
a fault. Once the IR module replaces this camera, set `camera_auto_detect=1` and drop both overlays
(unless it is also a clone).

`cmdline.txt` is stock (`quiet splash`, no isolation/tuning parameters).

## Camera

Added **2026-10-10**. Sold as "Raspberry Pi 5 Camera Module 5MP" (RAM Electronics, 450 EGP): an
**OV5647** clone (Camera v1.3 design) with the 22-pin Pi 5 ribbon bonded to the board. RGB, no IR —
a stand-in for development until the BOM's IR 160° module arrives.

| Item | Value |
|---|---|
| Sensor | OV5647, I2C `0x36`, detected on `i2c@88000` → `rp1-cfe 1f00110000.csi` |
| Modes | 640×480 @ 62 fps, 1296×972 @ 46, 1920×1080 @ 33, 2592×1944 @ 15 |
| Used by face | 640×480 @ 30 fps, `BGR888` (= R,G,B bytes in picamera2) |
| Tuning file | `/usr/share/libcamera/ipa/rpi/pisp/ov5647.json` |

> [!warning] Lessons paid for once
> - **Not detected ≠ software problem.** With the overlay loaded, `ov5647 ... i2c read error ... -121`
>   means the sensor did not answer on I2C at all — a seating / orientation fault. A raw scan of the
>   camera buses (nothing at any address) confirmed it before any config change was worth making.
> - **The connection is marginal.** Mid-session the sensor dropped off I2C (`Remote I/O error`,
>   `Camera frontend has timed out!`); a power-off reseat fixed it. Re-check with
>   `rpicam-hello --list-cameras` whenever frames stop.
> - **Never hot-plug the ribbon.** `sudo poweroff`, unplug, reseat, boot.
> - The Tasks-style `PiCameraSource` used to request `RGB888` (B,G,R in memory) and a 16:9 main
>   with a 4:3 `lores` (stretched face) — both fixed on branch `face/pi-litert-stream`.

## Hardware gaps

> [!danger] Two BOM items are absent
> | BOM item | Cost | Status |
> |---|---|---|
> | Raspberry Pi 5 (8GB) | 13,000 EGP | ✅ Present |
> | **AI HAT+ 26 TOPS** | 8,750 EGP | ❌ **Not attached** |
> | **Pi IR camera 5MP 160°** | 1,050 EGP | ⚠️ **Not attached** — OV5647 RGB stand-in in use (see [[#Camera]]) |
> | MAX30102 wristband | 95–520 EGP | ❌ Not verified (BLE stack is ready) |

**Evidence:**

- `lspci` shows only the BCM2712 PCIe bridge and the RP1 south bridge. No Hailo endpoint.
  `hailortcli` is not installed, there is no `/dev/hailo*`, and no hailo apt packages.
- ~~`rpicam-hello --list-cameras` → `No cameras available!`~~ — superseded 2026-10-10: lists
  `ov5647 [2592x1944 10-bit GBRG]` (stand-in camera, not the BOM IR module).

Everything in [[5.2 Phase Two Plan]] Phase 1 and Phase 2 that depends on the accelerator or camera
is therefore **entirely unvalidated on real hardware**. The 26 TOPS figure and all CV latency
budgets in [[3.2 Technical Description]] are, at present, assumptions.

> [!info] Open question, 2026-08-30
> Whether the accelerator is strictly required at all — as opposed to a CPU-only vision path with
> disciplined process management — is now an open question, not an assumption either way. See
> [[Pi Setup Plan#Open question — does the AI HAT+ turn out to be optional]]. The camera gap is
> unaffected by this — something has to feed frames in either case, and a USB webcam unblocks that
> immediately without waiting on the IR camera specifically.

## Interface readiness

| Interface | State | Needed for |
|---|---|---|
| Bluetooth / BLE | ✅ Working | MAX30102 wearable link ([[Physiology Subsystem]]) |
| I2C | ❌ **Disabled** — only `i2c-13`/`i2c-14` exist (internal HDMI DDC), no `i2c-1` | Sensors, direct MAX30102 if wired |
| SPI | ❌ **Disabled** (`dtoverlay=nospi10`) | Optional peripherals |
| GPIO | ✅ User in `gpio` group | Buzzer + vibration motor ([[3.1 System Architecture]] alert subsystem) |
| Camera (CSI) | ✅ OV5647 stand-in on CSI, manual overlay (2026-10-10) | Both vision models |
| PCIe | ⚠️ Connector free (nothing attached) | AI HAT+ **or** NVMe — [[Pi Setup Plan#The PCIe contention problem\|not both]] |

## Health baseline

| When | Idle temp | Throttled | RAM used | Notes |
|---|---|---|---|---|
| 2026-08-28 | 43.9 °C | `0x0` | ~582 MiB / 7.9 GiB | First survey |
| 2026-09-20 | 48.3 °C | `0x0` | ~567 MiB / 7.9 GiB | Still no camera / no Hailo |
| 2026-10-10 | 48–51 °C **under face load** | `0x0` | face process 133 MB RSS | Face stream live, 30 fps; standalone |

ARM clock 2.4 GHz both surveys. Re-measure under the full three-model workload — physiology gates
are defined relative to a *concurrent* baseline, not an idle one.

## Access note (2026-09-20)

Tailscale SSH to `100.113.107.122` answered `OK` interactively this session. Prefer **LAN + key**
for automation anyway — Tailscale check-mode can still demand browser re-auth mid-script. See
[[#Access]].

## Access note (2026-10-10)

Tailscale SSH to `khalifa@100.113.107.122` worked **non-interactively** (`ssh -o BatchMode=yes`)
for a whole session — no check-mode browser prompt. Useful when off-LAN, but check mode can still
fire; keep **LAN + key** as the default for anything scripted. `sudo` needs a password (no
`NOPASSWD`), so config changes are done by a human at the keyboard.

## Next steps

See [[Pi Setup Plan]] and [[Phone Subsystem]]. With a camera now on the Pi: run phone ONNX
alongside the face stream for the concurrent budget (G6), complete a successful driver calibration
on the Pi, and record a thermal soak. Wearable still blocks real PPG; the AI HAT+ question stays
open ([[Pi Setup Plan#Open question — does the AI HAT+ turn out to be optional]]).
