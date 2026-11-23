---
title: "Presentation 2026-11-24 — Final Blow"
tags:
  - demo
  - presentation
  - checklist
  - agent
status: current
updated: 2026-11-24
aliases:
  - Final Blow
  - Tomorrow presentation
  - Presentation checkup
---

# Presentation 2026-11-24 — Final Blow

↑ [[Home]] | [[Handoff 2026-11-23 Demo]] | [[Demo Prep 2026-11-23]] | [[Agent Guide]]

Tag: **`Final Blow`** on `main`. Night-of freeze for the 24 Nov live demo.

## What must be ON (agent checklist)

Do these in order before touching code or “fixing” anything.

| # | Thing | How to verify | If down |
|---|---|---|---|
| 1 | Pi Tailscale | `ssh khalifa@100.113.107.122 echo up` | Wait / ask user; relayed links drop |
| 2 | `rtdms-pi-user` | `systemctl --user is-active rtdms-pi-user` → `active` | `systemctl --user restart rtdms-pi-user` then `~/rtdms-pi/pi/deploy/check.sh --wait 120` |
| 3 | Camera + models | `check.sh` shows camera + face + distraction + physiology + fusion OK | Restart service; do **not** redeploy random branches mid-demo |
| 4 | `rtdms-dashboard` | `http://100.113.107.122:8000` (or LAN IP) loads | `systemctl --user restart rtdms-dashboard` |
| 5 | Phone Sahi APK / dev client | App open, paired to unit (BLE `RTDMS-Pi`) | Install preview APK from EAS; Settings → Sound on |
| 6 | Media + notification volume | Phone not silent | Alerts use TTS + notification channel |
| 7 | Garmin watch (optional) | Physio tile shows HR; ACK cancels SOS | BLE physio path; `ack_age_s` on `/physio` |
| 8 | Power | Official 27 W supply, short cable | Throttle bit must stay `0x0` in `check.sh` |

**Persistence (already set for tomorrow):** user linger `yes`; both user units **enabled** at boot. After a power cycle, wait ~2 min then run `check.sh --wait 120`. No sudo required for service restarts.

## Morning checkup (copy-paste)

From the laptop (Tailscale up):

```bash
ssh khalifa@100.113.107.122 'systemctl --user is-active rtdms-pi-user rtdms-dashboard; ~/rtdms-pi/pi/deploy/check.sh --wait 120'
```

Expect: both `active`, `READY: all checks pass` (BLE open-mode warning is OK for demo).

Dashboard: open `http://100.113.107.122:8000` (or Pi LAN IP if presenting off Tailscale). Press **F** for fullscreen. Prefer LAN/hotspot over Tailscale for the projector.

## Demo behaviour freeze

| Topic | Behaviour |
|---|---|
| SOS | WhatsApp relay + SMS only — **no 123 / emergency dial** |
| Watch “I’m OK” | Fresh `ack_age_s` (≤ 2 s) cancels phone SOS countdown |
| Phone alerts | Voice + notification sound while app is foreground; Settings → Sound and voice |
| Unresponsive → max | Wait survives blinks / wrist motion (eyes-open clear ~1.5 s) |
| Drinking | Held IR path + dashboard 1.5 s mean of `p_drinking` |
| Call | Sustained phone-at-ear latch |
| Texting / eating labels | Not reported to fusion |

## Agent rules for demo day

1. **Do not** merge unrelated branches (`phone/eating-mnv3`, `RTDMS-reset`, etc.) into the live Pi.
2. **Do not** change detection thresholds without a recorded session + user OK.
3. Prefer `systemctl --user restart …` over redeploy. If you must deploy: backup → one `tar|ssh` → md5 → restart → `check.sh`.
4. Keep frames/PII in `/tmp` or scratch; delete after use. `/tmp` is wiped on reboot.
5. Short answers; ask before changing what the system detects.

## Known soft spots (show carefully)

- Iris “looking away” can fire while looking ahead (gaze_v noisy at distance) — sit 50–80 cm, side angle, recalibrate on site.
- Hand at cheek can read as drinking briefly before call latch.
- Eye-closure alert is **1.5 s** (stricter than report 2–3 s).

## Where code lives

| Piece | Location |
|---|---|
| Git freeze | `main` @ tag `Final Blow` |
| Pi runtime | `~/rtdms-pi`, venv `~/rtdms/.venv`, unit `rtdms-pi-user` |
| Dashboard | `~/rtdms-demo/dashboard`, unit `rtdms-dashboard` :8000 |
| Camera stream / status | :8080 |
| Fusion / physio / alert | :8090 |
| App | `app/` — Expo project `sahi`, package `edu.aast.rtdms.sahi`, EAS project `01bc3e69-724b-4a2f-bb88-43d2ffb71563` |
