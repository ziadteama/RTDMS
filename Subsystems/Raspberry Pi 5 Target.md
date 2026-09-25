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
status: bare-stock-install
code_path: (deployment target)
language: Debian 13 trixie / arm64
surveyed: 2026-09-20
---

# Raspberry Pi 5 — Target Device

↑ [[Home]] | [[Models Index]] | Setup plan: [[Pi Setup Plan]]

The physical machine everything deploys to. First surveyed **2026-08-28**; re-checked over SSH on
**2026-09-20** (LAN `192.168.100.181` and Tailscale `100.113.107.122` both answered).

> [!warning] Current state: bare stock install
> The Pi is a clean Raspberry Pi OS install with **no project dependencies, no AI accelerator, and
> no camera attached**. Wearable not present either. See [[#Hardware gaps]].

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
| Installed Python pkgs | `numpy 2.2.4`, `picamera2 0.3.37` — **that's all** |
| Not installed | scipy, opencv, mediapipe, bleak, ultralytics, hailo-platform, torch, tflite-runtime, Docker |
| CPU governor | `ondemand` (max 2.4 GHz) |
| Pending updates | openssl / libssl3t64 **security** updates, ffmpeg libs |

### Boot configuration

`/boot/firmware/config.txt` is stock. Relevant lines:

```
#dtparam=i2c_arm=on      <- COMMENTED OUT
#dtparam=spi=on          <- COMMENTED OUT
camera_auto_detect=1
display_auto_detect=1
dtoverlay=vc4-kms-v3d
arm_boost=1
[pi5]
dtoverlay=nospi10
```

`cmdline.txt` is stock (`quiet splash`, no isolation/tuning parameters).

## Hardware gaps

> [!danger] Two BOM items are absent
> | BOM item | Cost | Status |
> |---|---|---|
> | Raspberry Pi 5 (8GB) | 13,000 EGP | ✅ Present |
> | **AI HAT+ 26 TOPS** | 8,750 EGP | ❌ **Not attached** |
> | **Pi IR camera 5MP 160°** | 1,050 EGP | ❌ **Not attached** |
> | MAX30102 wristband | 95–520 EGP | ❌ Not verified (BLE stack is ready) |

**Evidence:**

- `lspci` shows only the BCM2712 PCIe bridge and the RP1 south bridge. No Hailo endpoint.
  `hailortcli` is not installed, there is no `/dev/hailo*`, and no hailo apt packages.
- `rpicam-hello --list-cameras` → `No cameras available!`

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
| Camera (CSI) | ⚠️ Auto-detect on, but nothing connected | Both vision models |
| PCIe | ⚠️ Connector free (nothing attached) | AI HAT+ **or** NVMe — [[Pi Setup Plan#The PCIe contention problem\|not both]] |

## Health baseline

| When | Idle temp | Throttled | RAM used | Notes |
|---|---|---|---|---|
| 2026-08-28 | 43.9 °C | `0x0` | ~582 MiB / 7.9 GiB | First survey |
| 2026-09-20 | 48.3 °C | `0x0` | ~567 MiB / 7.9 GiB | Still no camera / no Hailo |

ARM clock 2.4 GHz both surveys. Re-measure under the full three-model workload — physiology gates
are defined relative to a *concurrent* baseline, not an idle one.

## Access note (2026-09-20)

Tailscale SSH to `100.113.107.122` answered `OK` interactively this session. Prefer **LAN + key**
for automation anyway — Tailscale check-mode can still demand browser re-auth mid-script. See
[[#Access]].

## Next steps

See [[Pi Setup Plan]] and [[Phone Subsystem]]. Immediate software path without camera/wearable:
phone ONNX still-image bench + shared video capture + fusion stub. Hardware still blocks live CV
and real PPG.
