---
title: "Project Log: 21-22 Nov 2026 (decisions, evidence, lessons)"
tags:
  - log
  - decisions
  - project
aliases:
  - Decision log Nov 2026
  - Project Log
status: current
period: 2026-11-21 to 2026-11-22
---

# Project Log: 21–22 Nov 2026

↑ [[Home]] | Where we are and what is next: [[Open Items and Next Steps]] | How the agents work: [[Orchestration Playbook]] | Setup: [[Dev Environment and Test Devices]]

One place that says **what was decided, why, and what evidence exists**. Each row links to the note
that holds the detail. Anything not measured says so. Raw hand-off messages between the agents are
archived in [[Coordination Board 2026-11]].

> [!abstract] State at the end of 22 Nov
> Merged to `main`: Pi runtime (`pi/`), phone↔Pi contract, WhatsApp relay (`relay/`), the Sahi app
> (English only, end-user structure, crash/SOS hardening, relay client) and three always-on rules.
> **Verified on real hardware:** the app installs and runs on a realme GT 6T; the app talked to the
> Pi's running camera server over Tailscale; the relay sent real WhatsApp messages end to end; a
> link-free SMS reached a recipient while the same text with a link did not.
> **Not yet verified:** the Pi runtime (`pi/`) on the Pi, Bluetooth between phone and Pi, the Pi
> hotspot, the crash detector on real motion, and any of it in a moving car.

> [!info] Overnight 22 Nov (01:40–04:30): phone eye calibration
> - **UI sweep and declutter** of every screen (PR #45, implemented by agy, reviewed and gated by MAIN).
> - **Camera server as a service** on the Pi (PR #46): `systemctl --user` unit, restarts on crash; boot start waits for `sudo loginctl enable-linger khalifa`.
> - **Contract v1.1** (PR #47): `phone_calibration` payload; the Pi uses only `closed_ratio` because phone EAR does not transfer across cameras. Detail: [[Eye Calibration]].
> - **Android controls fix** (PR #48): dropdowns squeezed labels into one letter per line on the realme; now a value + choice sheet.
> - **Pi side** (PR #49, docs #50): applied and verified on the running Pi with the fixture (200 + `calibrated (phone)`, poor → 400), test profile removed afterwards, no rollback needed.
> - **App side** (PR #52, docs #51): native `SahiFaceView` (CameraX + MediaPipe face landmarker, same EAR as the Pi), calibration math port, sync to the unit, guided 5-step flow in onboarding and Settings. Gates 520 tests; EAS dev build `00006dd7` compiled. **Not run on the phone yet.**
> - How: Sonnet orchestrators delegating to Codex (quota ran out mid-night), then agy and Claude subagents with cross-review; MAIN re-ran gates before every merge. One jest run showed a single flaky failure that did not reproduce in three reruns.

## Decisions

| # | Date | Decision | Why | Detail |
|---|---|---|---|---|
| D1 | 21 Nov | Phone↔Pi link is a **hybrid**: Bluetooth LE for alerts, heart data, settings and the crash trigger; Pi Wi-Fi hotspot only for video and clips. **Proposed, not measured.** | Android's no-internet Wi-Fi is fragile; alerts are tiny; dashcams use the same split | [[Phone-Pi Link]] |
| D2 | 21 Nov | Bluetooth tethering rejected as the main link | Apps cannot enable it, too slow for the preview, needs Classic Bluetooth which is off | [[Phone-Pi Link]] |
| D3 | 21 Nov | Android only | Silent SMS and calls need Android; iOS no-internet Wi-Fi is fragile | [[Mobile App]] |
| D4 | 21 Nov | New Pi code lives in a top-level `pi/` zone; shared contracts in `contracts/` | One feature must not touch three zones | `.cursor/rules/git-branching.mdc` |
| D5 | 21 Nov | **One GATT service** (the Garmin one) carries all phone characteristics | `bless` 0.2.6 dropped a second service on 2026-11-08 | `contracts/pi-link/CONTRACT.md` |
| D6 | 21 Nov | Two Sonnet orchestrators (Pi, app) work in parallel through a coordination board; Codex and agy do the coding | Parallel work without collisions; separate quotas | [[Orchestration Playbook]] |
| D7 | 21 Nov | Always-on rule: reuse first, files ≤ 300 lines, named patterns | Avoid piled-up files and duplicated code | `.cursor/rules/code-structure.mdc` |
| D8 | 21 Nov | **The app is English only**: no Arabic, no RTL | User decision | [[Mobile App]] |
| D9 | 21 Nov | **Sahi is an end-user product for the driver, not an admin tool.** Three tabs (Drive, Trips, Settings), hidden Diagnostics | The first design looked like an engineer's dashboard | [[Mobile App End-User Scope]] |
| D10 | 21 Nov | SOS countdown default 45 s (30/45/60), loud from second 0, contacts first, then a 15 s stage before dialing 123 that only auto-dials if the phone stays still | Pixel Watch uses 60 s; Egypt's 123 line has a known fake-call problem | `app/docs/ux/flow-5-sos.md` |
| D11 | 21 Nov | Fusion's `decide()` accepts the debounced `call` / `texting` flags | The IR pipeline already debounces and has no sustained time | `fusion/` |
| D12 | 22 Nov | **SOS SMS carries no link.** Plain coordinates, one part, ≤ 160 chars | Real test: coordinates arrived; the same text with a Maps link did not (cause unconfirmed) | [[WhatsApp SOS Relay]] |
| D13 | 22 Nov | **SOS goes WhatsApp first, SMS as backup**, through a team relay using an unofficial library (Baileys). Ban risk accepted by the user | User preference; SMS stays because WhatsApp needs data | [[WhatsApp SOS Relay]] |
| D14 | 22 Nov | The relay runs on the dev machine for now; the phone reaches it over Tailscale | No public exposure needed for a prototype | [[Dev Environment and Test Devices]] |
| D15 | 22 Nov | APK builds use Expo's cloud (EAS), not a local Android SDK | No JDK or SDK on the dev machine | [[Dev Environment and Test Devices]] |

## Evidence collected

| Claim | Evidence | Status |
|---|---|---|
| App runs on a real phone | realme GT 6T, Android 16, EAS dev build installed over `adb`, bundled from Metro | **verified** |
| App talks to the Pi | Typed the Pi's Tailscale address; the app read the live camera server's `/status` | **verified** (functional only; Tailscale relays, so no latency conclusions) |
| Relay sends real WhatsApp | Smoke test: register → opt-in → test SOS → `delivered`; user confirmed arrival | **verified** |
| Link-free SMS arrives, linked SMS does not | Hand-sent A (coordinates) arrived, B (same + link) did not, same Vodafone recipient | **verified once**; cause (carrier or recipient filter) **unconfirmed** |
| Pi runtime passes its gates | 154 tests, ruff and mypy --strict clean, in Docker on x86 | **verified in Docker only** |
| App passes its gates | tsc, eslint, 398 jest tests, token grep (re-run by MAIN before each merge) | **verified on x86** |
| Bluetooth phone↔Pi, hotspot, Garmin coexistence | Spike tooling written, never run | **not measured** |
| Crash detector on real motion | Replay tests only | **not measured** |

## Bugs found by running on a device, and their fixes

| Bug | How it showed | Fix / status |
|---|---|---|
| SMS permission blocked for a sideloaded APK | Android 13+ "restricted settings" dialog | Manual step (Settings → Apps → Sahi → Allow restricted settings). A Play install does not hit it. Onboarding must explain it |
| SOS result said "delivered" for WhatsApp but nothing arrived | The app was in **demo mode**, which used a fake relay answering "delivered" | Fixed in the app (demo sends nothing and says so); Demo switch moved to Diagnostics |
| `npm start` crashed in real mode | Node strip-only mode rejects a TypeScript constructor shorthand; the dry-run smoke test never loaded that file | Start flag changed to `--experimental-transform-types` (package.json and Dockerfile) |
| Red box "ExpoKeepAwake.deactivate rejected" | Returning to the app after switching away | Reported to the app agent; keep-awake needs guarding |
| Contract fixtures said 2024 but the incident id said 2026 | Pi orchestrator's CR-1 | Fixtures corrected; two Pi tests updated |
| Result screen said "Calling 123…" before any call | SOS screen | Fixed to show the real call state |
| First WhatsApp test "failed" | Number was mistyped in the first run | Retest to the right number delivered |

## Open product and technical questions

See [[Open Items and Next Steps]].
