---
title: "Eye Calibration (Phone-to-Pi EAR Ratio)"
tags:
  - subsystem
  - calibration
  - vision
  - face
  - pi
aliases:
  - Eye Calibration
  - phone eye calibration
status: deployed-camera-service-unverified-ble
updated: 2026-11-22
---

# Eye Calibration (Phone-to-Pi EAR Ratio)

↑ [[Home]] | Runtime: [[Pi Runtime]] | Models: [[Face Subsystem]], [[Distraction Subsystem]] | Contract: `contracts/pi-link/CONTRACT.md`

Cross-camera eye calibration transferring phone-measured eyelid closure characteristics to the [[Pi Runtime]] and [[Face Subsystem]] without transferring raw EAR values.

## Pi side

### Why and transfer math

Raw phone Eye Aspect Ratio (EAR) does not transfer to the Pi camera due to different mounting angles, lenses, and distances. The Pi uses only the ratio measured on the phone:

$$\text{closed\_ratio} = \frac{\text{ear\_closed}}{\text{ear\_open}}$$

- **Math**: $\text{ear\_closed}(\text{Pi}) = \text{closed\_ratio} \times \text{ear\_open}(\text{Pi})$. The baseline $\text{ear\_open}(\text{Pi})$ is the Pi's own (calibrated or default `0.30`, then adapted). Example: ratio `0.38`, Pi open `0.30` $\to$ closed `0.114`.
- **Adaptation**: `BaselineAdapter` recomputes $\text{ear\_closed} = \text{closed\_ratio} \times \text{adapted\_ear\_open}$ after every adaptation step. The existing floor ($\text{closed} + 0.05$) is unchanged; profiles without `closed_ratio` behave as before.
- **Scope**: Gaze and head-pose values stay from the Pi's own profile.

### Validation

Validated via `profile_from_phone` (`models/face/src/dms_face/calibration.py`) against `contracts/pi-link/schemas/phone_calibration.schema.json`:
- `source`: `"phone"`
- `closed_ratio`: finite float in `0.1..0.8`
- `quality`: `"good"` or `"fair"` (`"poor"` rejected)
- Eyelid delta: $\text{ear\_open} - \text{ear\_closed} \ge 0.04$
- Field types and no unknown keys.

Rejections return HTTP 400 `{"ok":false,"error":reason}` or a failed BLE `command_result` with the reason. The old profile is retained and status shows `"calibration failed: <reason>"`.

### Integration paths

- **HTTP**: `POST /calibrate` with a JSON body (`models/distraction/scripts/stream.py`). An empty body runs the legacy Pi-camera routine.
- **BLE**: command `{"cmd":"calibrate","profile":{...}}` in `pi/`. Calibrate without `profile` now starts the camera run (the unused `calibrate_requested` flag was removed).
- **Pipeline hand-off**: lock-guarded and applied outside the lock. The profile is persisted to `profiles/<name>.json` with `closed_ratio`.
- **Status output**: `"calibrated (phone)"`, `calibrated: true`, `calibration: "ok"`.

### Tests and deployment

- **Tests**: `models/face` 93 passed (new `test_phone_calibration.py`), `models/distraction` 125 passed + 21 phone tests when `models/face` is on the path, `pi/` 167 passed with `ruff` and `mypy --strict` clean. PR: #49 (`pi/phone-calibration`).
- **Deploy result (2026-11-22, Pi 100.113.107.122)**: User-approved live deployment (backup `~/rtdms/.bak-20261122-024539`). 3 files copied, `systemctl --user restart rtdms-camera`. Verified `/status` 200, POST fixture $\to$ 200 + `"calibrated (phone)"` + saved `ear_closed` 0.114 (`0.38 x 0.30`), POST quality poor $\to$ 400 `"poor eye signal"`, empty POST starts camera run. Test profile deleted and service restarted (no profile existed prior); no rollback needed; `throttled=0x0`. Note: the `pi/` runtime itself is not running on the Pi.

### Limitations and unvalidated assumptions

- **Camera geometry**: IR camera, mounting angle, and 180 degree rotation make EAR scale differ. The assumption that closed/open scales alike across cameras is NOT yet validated on real drivers (requires calibrating drivers both ways and comparing phone-derived closed EAR against the Pi's own two-phase closed value).
- **Open baseline propagation**: Ratio is applied to the Pi's adapted open value, so a bad Pi open baseline propagates.
- **Feature limits**: No gaze or head-pose from phone.
- **Hardware gaps**: BLE path is untested on hardware. The Pi's own two-phase run remains the fallback.

## App side

Code: `app/src/calibration/`, `app/modules/sahi-native/` (`SahiFaceView`), `app/src/services/calibration-sync.ts`, `app/src/screens/calibration/`. App note: [[Mobile App]]. UX: `app/docs/ux/flow-9-eye-calibration.md`.

### What it measures

The phone's front camera measures the driver's own Eye Aspect Ratio twice, eyes open and eyes closed. Only the ratio `closed_ratio = ear_closed / ear_open` matters to the Pi (see [[#Why and transfer math]]); the raw values travel in the payload for checks but are not applied.

- **`SahiFaceView`**: native Expo view (CameraX front camera + MediaPipe Face Landmarker, `face_landmarker.task` bundled in the app). `onFace` events at 15 Hz or less carry EAR, yaw, pitch, face box and luma. EAR is an exact port of `models/face/src/dms_face/metrics.py`. EAR is marked invalid when `|yaw| > 30` or `|pitch| > 25`.
- **Profile maths**: pure TypeScript port of `build_profile` (`app/src/calibration/build-profile.ts`). First 2 s of each phase discarded (settle), then median + MAD. Rejected unless open minus closed EAR is at least 0.04. Quality from SNR = separation / noise: 40 or more `good`, 20 or more `fair`, else `poor`. Failure reasons: `too_dark` (luma below 40), `no_face`, `head_turned`, `eyes_not_shut`, `too_few_samples`.
- **Payload**: `contracts/pi-link/schemas/phone_calibration.schema.json`, stored in app settings as `eyeCalibration` (with `syncedAt`).

### Flow

Intro, framing (oval + three ticks for face in oval, light, head straight), eyes open 10 s, eyes closed 3 s (voice and haptic cue at the end), result (grade, Save, Retry, sync line), plus failure screens per reason above. Entry points: onboarding (skippable step after connect), Settings > Unit "Eye calibration" (this one), Settings > Unit "Driving position" (the existing Pi-camera calibration, unchanged), and a hint link on Drive. Screens: `app/docs/ux/flow-9-eye-calibration.md`.

### Data and privacy

- No frame is stored or sent; only the numeric payload leaves the phone.
- The camera runs only while the view is mounted (unbound on detach).
- `FakeFaceSource` replaces the camera on web, in Jest and in demo mode.

### Sync to the Pi

`calibration-sync.ts` sends `POST /calibrate` over HTTP now; a BLE `calibrate` command is a documented hook, not wired. It sends when `eyeCalibration` exists with `syncedAt` null and the unit is online, retries on reconnect, and sets `syncedAt` on 200. A 400 is not retried for the same calibration. Demo mode sends nothing and never marks synced.

### Status and limits

- **Tested**: Jest (maths, sync, settings, `FakeFaceSource`, face metrics); sync against the mock Pi only.
- **Not verified on the device**: camera and face view on the real phone, voice and haptic cues, real sync to the Pi.
- **State at writing**: the native view, maths, store and sync are on branch `app/phone-calibration`; the guided screens and entry points described above were not on that branch yet.
- Pi-side limits (cross-camera assumption unvalidated, BLE untested) are listed under [[#Limitations and unvalidated assumptions]].
