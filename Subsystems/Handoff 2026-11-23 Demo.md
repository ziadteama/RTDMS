---
title: "Handoff 2026-11-23 Demo"
tags:
  - handoff
  - demo
  - status
status: current
updated: 2026-11-23
aliases:
  - Demo handoff
---

# Handoff 2026-11-23: live demo prep (paused)

↑ [[Home]] | [[Demo Prep 2026-11-23]] | [[Open Items and Next Steps]] | [[Agent Guide]]

> [!abstract] For the next agent: read this, then [[Demo Prep 2026-11-23]]
> We were getting the **live demo** ready for the presentation on **24 Nov 2026**: a full-screen
> dashboard on the Pi showing what the system sees, with the face mesh, eyes, phone call,
> drinking, watch heart rate and the alert, while the phone app and the Garmin watch react.
> The user (Youssef, face-zone owner) tested on the real Pi and we fixed issues **from recorded
> sessions**. We paused with two problems open: **"looking away" fires while looking ahead**, and
> **a hand or phone at the cheek reads as drinking**.

## Where everything is

| What | Where |
|---|---|
| Pre-release (everything below merged together) | branch `demo/pre-2026-11-23`, GitHub pre-release tag `demo-2026-11-23-pre` (tag at 2dde7b3; the branch may be ahead with docs/tools) |
| Live dashboard + Pi test tools | branch `demo/live-dashboard`: `demo/dashboard/` (server, page, tests, README), `demo/tools/` (recorder, analyser, live watch) |
| Camera pipeline changes | branch `distraction/occlusion-gate` (name is historical: the gate itself was removed). Full-res face crop, texting removed, eating/texting never reported, frozen eyes-open reference, post-calibration grace, `p_drinking`, diagnostic fields |
| Runtime camera draws the mesh | branch `pi/camera-demo-flags`, **PR #94** (open) |
| Write-up, decisions D29-D35, report audit | branch `docs/demo-prep-2026-11-23`: [[Demo Prep 2026-11-23]], [[Project Log 2026-11]], [[Open Items and Next Steps]] |
| Local worktrees (dev machine) | `C:\Users\youss\projects\RTDMS-dashboard`, `-occlusion`, `-pi-flags`, `-docs`, `-pre`. The main checkout `RTDMS` is on the user's own branch `phone/eating-mnv3` (19 commits, **never pushed**: the user said "not now"); do not touch it |
| Someone else's work | `C:\Users\youss\projects\RTDMS-reset`, branch `pi/perclos-reset-after-calibration`, **uncommitted**, from the "Remote control" session: a camera `/reset` command, its own post-calibration grace, app BLE/i18n changes. It overlaps `drowsiness.py` / `stream.py` / `app/src/i18n/en.ts`. Do not edit it; reconcile with its owner before merging |

**On `main` since 23 Nov evening:** PR #94 (mesh), #95 (camera pipeline), #96 (dashboard + tools), plus this docs PR.

## The Pi right now

- Reach: `ssh khalifa@100.113.107.122` (Tailscale, key auth; relayed and drops sometimes). No sudo password (by design): a reboot needs the user; services restart without it: `systemctl --user restart rtdms-pi-user rtdms-dashboard`.
- Running: `rtdms-pi-user` (runtime owns the camera: `--camera --rotate 180 --stream-port 8080 --ble --buzzer none --port 8090`) and `rtdms-dashboard` (`~/rtdms-demo/dashboard/server.py`, :8000), both enabled at boot. Readiness: `~/rtdms-pi/pi/deploy/check.sh --wait 120`.
- Deployed code = `demo/pre-2026-11-23` exactly (md5-checked: camera scripts, `rtdms_distraction` roi/config/facemesh/pipeline, runtime `sources.py`, dashboard). **Pi-only, not in git:** `hires_crop: true` under `facemesh:` in `~/rtdms/distraction/configs/pipeline.yaml`.
- Backups of every replaced file: `~/rtdms-pi/.bak-20261123-*/code.tgz` (171118 ... 193139). Old eye profile: `~/rtdms/distraction/profiles/default.json.bak-before-demo-recal`.
- **Deploying:** `pi/deploy/deploy.sh` does not work from Git Bash on Windows (Windows `find`, reports "0 file(s) differ"). Build a folder with `git show <ref>:<path>`, send it in **one** `tar | ssh` call that first backs up the targets, then check every md5. Restart `rtdms-pi-user` for camera/runtime files, `rtdms-dashboard` for the dashboard.
- The Pi rebooted by itself 5 times on 23 Nov (at least 2 from being moved); logs end abruptly. Expect it; `/tmp` is wiped at boot.

## How we worked (keep doing this)

1. The user describes a symptom.
2. Record a session on the Pi with `demo/tools/session_log.py`: one frame plus the full status every 0.5 s, run detached (see `demo/tools/README.md`).
3. Analyse it with `demo/tools/analyse.py`: a timeline plus frame sheets.
4. Show the user the numbers and frames, and agree the fix.
5. Change on the right zone branch, test, deploy with backup and md5 check, verify live.

Three guesses this evening turned out wrong once measured (the eyes gate, the calibration drift, the drinking threshold). Frames contain people: keep them in `/tmp` or the scratchpad and delete them after use.

The user prefers short answers and quick iterations, gets frustrated by long procedures (an A/B test was rejected as too much), and wants to decide on behaviour changes. Ask before changing what the system detects.

## Next steps, in order

1. **Looking away while looking ahead.** The camera status now has `d_yaw`, `d_pitch` (from the calibrated neutral), `gaze_h`, `gaze_v` and `gaze_dev`. One live reading: head 17 deg (limit 25) but `gaze_dev` 0.183 > 0.16, i.e. the **iris branch** of `dms_face.state._evaluate_gaze`. Earlier calibrations put `gaze_v0` anywhere from 0.01 to 0.44, so the vertical iris ratio is noise at this face size.
   - Record a 1-minute test: ahead 20 s, head left / right / down, eyes-only left/right, ahead 20 s.
   - Pick the fix from the numbers: horizontal-only gaze, a higher `cfg.gaze.deviation_threshold` set in `Drowsiness`, or head pose only.
   - The head-pose rule already covers looking down (report: off-road > 2 s).
2. **Hand or phone at the cheek reads as drinking** (66-89 % before the classifier switches to "call").
   - Proposed "call wins": in `demo/dashboard/server.py` `DrinkDebounce.update`, a frame whose top class is `call` scores 0.
   - The user hasn't approved it yet; ask.
3. **App calibration wording** (no functional change needed):
   - Step 1 "Look ahead and blink normally (don't open your eyes wide)".
   - Add "calibrate again if the unit or seat moves".
   - Optional: drop the Diagnostics "Texting" row and the "(EAR)" label, and the texting phase in demo mode.
   - Coordinate with the `RTDMS-reset` work: it edits `en.ts` too.
4. **Merge path:**
   - Reconcile `pi/perclos-reset-after-calibration` with `distraction/occlusion-gate` (both add a post-calibration grace to `drowsiness.py`).
   - Then PRs per zone (PR #94 exists), docs last.
   - The dashboard's Reset button needs that branch's camera `/reset`.
5. **Before the demo:**
   - Camera 50-80 cm from the driver, 25-30 deg to the side (side = good drinking/phone, frontal = good eyes).
   - Recalibrate in the final position.
   - Official 27 W supply with a short cable fixed in place.
   - Dashboard on the laptop over LAN or the Pi hotspot rather than Tailscale; press F for full screen.
6. **Report vs code:** the eye-closure alert fires at 1.5 s, but the report says 2-3 s. Decide whether to change the code or the report wording.

## Not done / not verified

- None of today's fixes has been tried with the phone app or the Garmin watch connected; the watch link showed "not connected" all evening.
- No Docker verify for `pi/` (no Docker on the dev machine); the Windows run matches main apart from POSIX-only tests and the flaky `test_bench_link`.
- The Garmin `rr_stream.prg` built with the local SDK (9.3.0) earlier today; it was never installed on the watch from this session.
