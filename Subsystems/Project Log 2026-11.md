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

> [!info] Day 22 Nov (09:40–17:00): first device run, Bluetooth link, relay as a service
> - **Eye calibration run on the realme** (build `00006dd7`): camera preview was black and every check failed; fixed in PR #55 (details under *Bugs*). With build `ba793815` the preview shows the face, the face model reports it at about 10 Hz and the calibration finishes. Sync to the Pi is **not yet verified** (Pi camera server stopped).
> - **Pi camera detached on purpose.** The ribbon is out ("we don't need it for now"), so `rtdms-camera` is disabled on the Pi. The Pi is reached over Tailscale; for a while it was cabled straight into the dev machine and shared its internet (see [[Dev Environment and Test Devices]]).
> - **Bluetooth LE link built end to end** (contract v1.2 #57, Pi #58/#59, app #60/#61): BLE first, HTTP fallback. Pi side runs as the user service `rtdms-pi-user` and advertises `RTDMS-Pi`. Bench from the dev machine met the CPU, memory and alert-latency budgets; command round trip and scan-inclusive reconnect missed (numbers in [[Phone-Pi Link]]).
> - **Dev "open mode" (no code)**: #62/#63/#64. The phone finds `RTDMS-Pi` by scanning and connects with no QR and no token. DEV ONLY. A real pairing mode is planned and tracked in [[Open Items and Next Steps]].
> - **First phone ↔ Pi Bluetooth connection seen:** the Pi listed the phone as an LE central, the Pi's HTTP port was dead, and the app still showed "unit connected" with the Pi's live health (CPU 1 %, 44 °C, 5.14 V, uptime). Link row text on Diagnostics, screen-off behaviour and fallback were **not yet checked**.
> - **WhatsApp relay now a systemd user service** (#65, restart on crash tested with `kill -9`). The saved WhatsApp session turned out to be **logged out (401)**; re-linked the same evening (script `relink-whatsapp.sh`). Boot start needs one sudo step (`loginctl enable-linger`).
> - How: Sonnet orchestrators (Pi, app) delegating to Codex (back after 23:01), agy and Claude subagents with cross-review; MAIN re-ran every gate and merged #45–#65. One orchestrator reported green gates that did not reproduce on the first cold run (see *Lessons*).

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
| D16 | 22 Nov | **Phone measures eye closure, Pi uses the ratio.** The phone sends only `closed_ratio`; the Pi sets `ear_closed = ratio × its own ear_open`. Raw EAR does not transfer between cameras | Different angle, lens and distance | [[Eye Calibration]] |
| D17 | 22 Nov | **Bluetooth first, HTTP fallback.** HTTP stays for video, clips and Tailscale dev testing | User choice; keeps dev testing working | [[Phone-Pi Link]] |
| D18 | 22 Nov | **Pi efficiency first** (user requirement): BLE ≤ 2 % of one core, ≤ 25 MB extra RSS, no idle wake-ups beyond the timers, alert p95 ≤ 300 ms, vision fps drop ≤ 3 % | The Pi also runs the models | `.cursor/rules/pi-performance-pipeline.mdc` |
| D19 | 22 Nov | Contract v1.2 (CR-BLE-RATES): alert on change + 1 Hz keep-alive, status 1 Hz on change + 5 s keep-alive, physio ≤ 1 Hz; phone stale after 3 s; no HTTP polling while BLE is online | D18 | `contracts/pi-link/CONTRACT.md` |
| D20 | 22 Nov | **Dev BLE open mode: no code, for now.** Pairing mode later (Pi accepts the first phone for 2 minutes after a button press; the app stores a server-issued token) | User: "for now make it with no codes… doc that we will make pairing mode later" | [[Phone-Pi Link]] |
| D21 | 22 Nov | The Pi camera stays detached for now; `rtdms-camera` is disabled until the ribbon is back | User | [[Open Items and Next Steps]] |
| D22 | 22 Nov | The WhatsApp relay runs as a systemd **user** service on the dev machine | It was a hand-started process with no restart | [[WhatsApp SOS Relay]] |
| D24 | 23 Nov | **Heart rate is not a fatigue detector.** Live roles: vital-sign check (emergency path) and quality gate; the MPD-DF fatigue score runs in shadow mode (weight 0); fusion never alerts on physiology alone; 2 h drive-time break reminder | MPD-DF: HR 0.76, drive time 0.84, HR on top of time +0.006 | [[Physiology New Approach]] |
| D25 | 23 Nov | **Two clocks:** phone = what time it is (all payload `t` = UTC epoch ms in phone time), Pi monotonic = how long and which came first; watch samples timed from `watch_ms`, not arrival | Payload `t` used three clocks; buffered watch packets were stamped on arrival | [[Physiology New Approach]] |
| D26 | 23 Nov | Pi saves no heart data (research CSV only with `--csv` / `RESEARCH_LOG=1`); phone keeps trip HR on the phone with an off switch and delete-with-trip | Report §4.3; user choice | [[Physiology New Approach]] |
| D27 | 23 Nov | The Garmin FR265 replaces the MAX30102 bracelet and the vibration motor (wrist vibration + "I'm OK"); unresponsive-driver SOS in scope | User | [[Physiology New Approach]] |
| D28 | 23 Nov | **The eating / drinking / food model is not part of fusion** until it is figured out and validated; `decide()` ignores those outputs (test) | User | `fusion/` |

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
| Red box "ExpoKeepAwake.deactivate rejected" | Returning to the app after switching away | Fixed in PR #55: `useKeepAwake(undefined, { suppressDeactivateWarnings: true })` |
| Eye calibration camera preview black, all three checks failing | First run of dev build `00006dd7` on the realme (22 Nov); camera indicator on, CameraX logged `Failed to get Surfaces` | React Native never measures native children, so the preview stayed 0×0 and CameraX had no Surface: no preview, no frames for the face model. `SahiFaceView` now measures and lays out the preview itself (PR #55). Verified on the phone with build `ba793815`: face found at about 10 Hz, calibration finished |
| Eye calibration preview black, all three checks failing | First run of build `00006dd7`: camera indicator on, CameraX logged `Failed to get Surfaces` | React Native never measures native children, so the preview stayed 0×0. `SahiFaceView` now measures and lays out the preview itself, plus a TextureView (PR #55). Verified with build `ba793815` |
| App shows "failed to load" after installing a new build | Metro (running in web mode) had no `react-native-ble-plx` in `node_modules` of the main checkout; I had installed it only in a temporary copy | `npm install` in the main checkout and restart Metro with `--clear`. After merges the phone can also keep an old bundle: restart Metro, force-stop the app and reload |
| Pi camera service crash-looping every 3 s after a reboot | Linger made it start at boot with no camera attached (`stream.py` exits 0 when it finds no camera, so systemd just restarts it) | `rtdms-camera` disabled. Fixed properly in #68: `stream.py` exits 1 and the unit backs off (30 s, stops after 5 failures in 10 min); deployed and checked on the Pi (backup `~/rtdms/.bak-20261122-171235`). Re-enable when the ribbon is back |
| Pi BLE service crashed on start; unpaired centrals dropped | `bless` property enums are `Flag`, not int; the Pi's wireplumber also published an encrypted BLE-MIDI service | Fixed in #58; wireplumber BLE-MIDI disabled with a user config on the Pi (outside git) |
| Ruff errors merged with #58 | My review ran `docker verify` on a stale image, which also silently skipped new tests | Fixed in #62. **Always run `docker compose -f pi/compose.yaml run --build --rm verify`** |
| Dev machine disk "full" | `/tmp` is a 3.9 GB RAM-backed tmpfs and held 1.8 GB of downloaded APKs | Old APKs deleted; keep APKs out of `/tmp` |
| WhatsApp relay logged out | After switching the relay to a service it reported `whatsapp_logged_out` (401) | Re-linked at 17:05 with `relay/deploy/relink-whatsapp.sh` (old session kept renamed). Survives restart and `kill -9`. Unknown whether the session died before the switch. A QR printed by the terminal tool did not reach the user: render a PNG instead |
| Contract fixtures said 2024 but the incident id said 2026 | Pi orchestrator's CR-1 | Fixtures corrected; two Pi tests updated |
| Result screen said "Calling 123…" before any call | SOS screen | Fixed to show the real call state |
| First WhatsApp test "failed" | Number was mistyped in the first run | Retest to the right number delivered |

## Lessons from the day

- **Never trust an orchestrator's "gates green".** MAIN re-runs every gate in a clean copy. Twice a first cold run of `jest` failed (#52, #61, #63: `controls.test.tsx` timing out at 16 s) and then passed three times; cause not found, follow-up logged.
- **Stale Docker images lie.** `--build` is required for the Pi verify, otherwise new tests are skipped.
- **Check a native view on the device early.** A black preview cost three builds; a 0×0 native child is the first thing to suspect.
- **Native change means a new APK; JS-only change loads from Metro.** The app can still show an old bundle until Metro is restarted and the app force-stopped.
- **Shared scratch folders collide.** Two orchestrators overwrote each other's briefs; each now writes under its own `/tmp/claude-1000/<name>/`.
- **Don't screenshot the user's phone to debug.** Read the app's own text (`uiautomator dump` when the app is in the foreground) or ask for a screenshot.
- **Secrets stay outside git.** The Pi sudo password lives in `~/RTDMS-coord/secrets/pi.env` (mode 0600); the pairing QR with the token is only in that folder.

### Evening of 22 Nov: phone side closed

- User tried the Bluetooth link on the realme: no-code connect, reconnect, and Bluetooth off/on all work. Finding: with Bluetooth off the app showed the raw "device powered off" error. Fix #72: the link exposes `btOff`; the Drive banner and the Settings status say "Bluetooth is off".
- Cleanup: 12 agent worktrees and about 60 merged branches removed; only `main` remains. Root-owned Docker files in worktrees are removed through an alpine container.
- New note [[MVP Readiness]]: phone side is enough for a demo; the full chain still needs camera + Bluetooth + buzzer on the Pi, a real alert session, the real test SOS, pairing mode and a car test.
- Decision D23: the phone work is parked; next focus is heart rate / HRV (`models/physiology/`).

### 23 Nov: physiology pivot

- Reviewed the HR/HRV work end to end: the model and code are sound; the fatigue claim is not supported (D24).
- P0 done on two branches, not merged: `fusion/physio-guard` (physiology no longer changes live alerts; fusion 8, Pi 207 tests pass) and `physio/no-default-log` (physiology 132 pass; 5 pre-existing ruff errors in `tools/mpddf_*.py` left alone).
- Watch on the dev machine's USB is in Garmin mode (`091e:0003`, `garmin_gps` driver), not MTP; no Connect IQ SDK, Java or MTP client here yet.
- Plan: [[Physiology New Approach]].

### Night of 23 Nov: heart-rate plan carried through (user asleep, full orchestration)

- Merged: #77 packet v2 + WatchClock + HrStream, #78 fusion EmergencyMonitor / ShadowTracker /
  BreakReminder + D28 guard, #79 contract v1.3, #80 app v1.3, #81 MPD-DF shadow score, #83 Pi
  wiring, #84 watch round-trip fix. Draft #82 watch app (not compiled).
- Deployed to the Pi (`~/rtdms-pi`, backups `.bak-20261123-*`); over-the-air test with the dev
  machine acting as the watch passed; 0.35 % of one core while streaming. Evidence table in
  [[Physiology New Approach]].
- Codex implemented the core pieces; agy did read-only cross-reviews and found **6 real defects**
  that tests had missed (wall clock passed as the monotonic clock → payload `t` near 1970;
  incident window on wall time → empty clips; whole physio report cached → ACK hidden for 1 s;
  double SOS over a pending crash SOS; HTTP `/health` missing diagnostics; incident id from
  monotonic time). Two of its claims were wrong and were not applied (connect-time clock write is
  the auth signal; `snapshot.t` is never 0).

Lessons:
- **Codex errors can hide behind unrelated stderr.** Its usage limit showed only as a Notion MCP
  auth line in stderr; the real message was in `events.jsonl` (`turn.failed`). Codex quota ran
  out at ~01:30 (resets 05:57); the orchestrator finished the Pi wiring itself.
- **agy writes headless only with `--dangerously-skip-permissions`** (not approved), so agy stays
  the read-only reviewer; its reviews paid for themselves.
- **Docker images copy only listed paths:** a runtime artifact (the shadow model) must be added to
  `pi/Dockerfile`, or tests pass locally and fail in Docker.

## Open product and technical questions

See [[Open Items and Next Steps]].
