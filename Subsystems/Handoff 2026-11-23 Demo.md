---
title: "Handoff 2026-11-23 Demo"
tags:
  - handoff
  - demo
  - status
status: superseded
updated: 2026-11-24
aliases:
  - Demo handoff
---

# Handoff 2026-11-23: live demo prep

↑ [[Home]] | [[Presentation 2026-11-24]] | [[Demo Prep 2026-11-23]] | [[Open Items and Next Steps]] | [[Agent Guide]]

> [!success] Superseded for presentation day
> Use [[Presentation 2026-11-24]] (tag **`Final Blow`** on `main`). This note keeps the 23 Nov
> history and open soft spots.

## Where everything is (24 Nov morning)

| What | Where |
|---|---|
| Presentation freeze | `main` @ tag `Final Blow` |
| Live dashboard + Pi tools | `demo/dashboard/`, `demo/tools/` on `main` |
| Local worktrees | `RTDMS-held-demo` (demo night), `RTDMS-app` (Metro), `RTDMS` may be on `phone/eating-mnv3` — **do not merge eating into the Pi for the demo** |

## The Pi

- Reach: `ssh khalifa@100.113.107.122` (Tailscale).
- Boot persistence: linger **on**; `rtdms-pi-user` + `rtdms-dashboard` **enabled** and were `active` / READY on freeze night.
- Restart without sudo: `systemctl --user restart rtdms-pi-user rtdms-dashboard`.
- Readiness: `~/rtdms-pi/pi/deploy/check.sh --wait 120`.
- `/tmp` wiped on reboot; Pi-only `hires_crop: true` in distraction `pipeline.yaml`.

## Soft spots still true

1. Looking away while looking ahead (iris / gaze_v noise) — recalibrate on site, sit closer.
2. Hand at cheek can score as drinking before call latch.
3. Report says eye closure 2–3 s; code alerts at **1.5 s**.

## App freeze notes (Final Blow)

- SOS: WhatsApp + SMS only (no 123 dial).
- Watch ACK (`ack_age_s`) cancels SOS countdown.
- Foreground alert sound via TTS + notification channel.
