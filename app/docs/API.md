# Pi API, as Sahi uses it

Base URL: `http://10.42.0.1:8080` (the Pi's own hotspot), configurable in Settings → Pi address.
Plain HTTP + JSON, no auth (the hotspot's WPA2 password is the access control). Types live in
[`src/pi/types.ts`](../src/pi/types.ts); parsers in [`src/pi/parse.ts`](../src/pi/parse.ts) turn
anything malformed into `null`, never a guess.

| Method | Path | On the Pi today | In `mock-pi/` | In demo mode | App uses it for |
|---|---|---|---|---|---|
| GET | `/stream.mjpg` | ✅ `stream.py` | ✅ placeholder frames | — | Live view, calibration |
| GET | `/status` | ✅ `stream.py` | ✅ | ✅ | Live tab, trips, crash extras (5 Hz) |
| POST | `/calibrate` | ✅ `stream.py` | ✅ | ✅ | Guided calibration |
| GET | `/alert` | 🆕 proposed | ✅ | ✅ | Color, notification, voice, haptics (5 Hz) |
| GET | `/physio` | 🆕 proposed | ✅ | ✅ | Heart group on Live (1 Hz) |
| GET / PUT | `/settings` | 🆕 proposed | ✅ | ✅ | Settings → Driver / Detection |
| POST | `/test_alert` | 🆕 proposed | ✅ | ✅ | Settings → Test alert |
| GET | `/health` | 🆕 proposed | ✅ | ✅ | Pi tab (1 Hz while visible) |
| POST | `/incident` | 🆕 proposed | ✅ | ✅ | Crash / SOS: keep the ring buffer |
| GET | `/incidents` | 🆕 proposed | ✅ | ✅ | Trips → Clips on the Pi |
| GET | `/incidents/<id>/clip.mp4` | 🆕 proposed | ✅ sample clip | bundled clip | Incident player + download |
| GET | `/incidents/<id>/data.jsonl` | 🆕 **added by the app** | ✅ | ✅ | Incident sensor timeline |
| GET | `/incidents/<id>/meta.json` | 🆕 proposed | ✅ | — | (not read by the app yet) |
| POST | `/system/restart`, `/system/shutdown` | 🆕 proposed | ✅ (logged, ignored) | ✅ | Pi tab → Controls |

A 404 from a proposed endpoint means "this Pi runs an older `stream.py`": the app hides that
feature (e.g. no Heart group, a "this Pi does not report fusion alerts yet" banner) and retries
every 30 s. It never fills the gap with its own logic.

## `GET /status` (exists)

Exactly what `models/distraction/scripts/stream.py` `pipeline_loop` builds. Keys under
`drowsiness` come from `scripts/drowsiness.py` `Drowsiness.feed`, keys under `hybrid` from
`scripts/hybrid.py` `Hybrid.feed` (minus `onsets` and `ms`). Optional keys depend on flags.

Before the first frame (`Shared.status` initial value, no `temp_c`):

```json
{"fps": 0, "face": false, "baseline": 0, "levels": {}, "ms": {}}
```

`stream.py --drowsiness --hybrid --no-detect` (the v2 setup the mock imitates):

```json
{
  "fps": 14.3, "face": true, "baseline": 1, "levels": {},
  "ms": {"capture": 1.2, "facemesh": 18.9, "drowsiness": 6.1, "v2_phone": 22.4},
  "temp_c": 64.2,
  "drowsiness": {
    "state": "drowsy", "reasons": ["perclos high"], "perclos": 0.312, "perclos_valid": true,
    "blink_rate": 9.5, "closure_ms": 2400, "openness": 0.31, "face": true,
    "calibrated": true, "message": "calibrated", "ms": 6.1
  },
  "hybrid": {"face": true, "call": false, "texting": true, "action": "texting", "p": 0.91, "ear": 0.03, "lap": 0.84}
}
```

Without `--no-detect`, `levels` holds the release box rules (`{"phone_right_ear": "alert", "drinking": "none"}`).

> [!warning] Two names that mislead
> - `hybrid.ear` is the **phone-at-ear** probability, not the eye aspect ratio.
> - `stream.py` does not expose the eye aspect ratio at all. The app shows `drowsiness.openness`
>   (the face subsystem's calibrated, smoothed eye openness) as "Eye openness".

`drowsiness.state` values: `starting` (before the first report), and `dms_face` `DriverState`
`unavailable | alert | distracted | warning | drowsy`. An unknown value parses as `unavailable`.

## `POST /calibrate` (exists)

No body. Response `{"ok": true}`. The pipeline thread then runs 10 s eyes open + 3 s eyes closed;
the result appears in `/status` → `drowsiness.message`: `"calibrating"` → `"calibrated"` or
`"calibration failed: <reason>"`. The app's calibration screen times the two steps and reads that
message; nothing else is needed.

## `GET /alert` (proposed)

The latest `fusion/src/dms_fusion` `decide()` result:

```json
{"pattern": "repeated", "reasons": ["face drowsy"], "t": 1732117202.4}
```

`pattern` ∈ `none | short_beep | repeated | continuous | max` (`AlertPattern`, fusion's order).
`t` = Pi time of the decision. **This is the only input to the phone's alert output** (notification,
voice, haptics, state-indicator color). See [DESIGN.md](DESIGN.md) for the color mapping.

## `GET /physio` (proposed)

```json
{
  "watch_connected": true,
  "hr_bpm": 71,
  "rr_ms": [845, 850],
  "fatigue_probability": 0.31,
  "hrv": {"state": "valid", "mean_hr_bpm": 70.2, "rmssd_ms": 35.1, "quality": "good", "coverage": 0.93},
  "t": 1732117202.4
}
```

`hrv` is `models/physiology` `HrvSnapshot.to_dict()` trimmed to what the app shows (same names):
`state` ∈ `warmup | valid | degraded | bad | stale`, `quality` ∈ `good | degraded | bad`.
`fatigue_probability` is the physiology model's output, `null` until it has a trusted window; the
app shows it as a percentage and applies no threshold. `hrv` is `null` when the watch is off.

## `GET /settings`, `PUT /settings` (proposed)

```json
{
  "profile": "default",
  "profiles": ["default", "driver-2"],
  "sensitivity": "normal",
  "eye_closure_s": 2.0,
  "offroad_gaze_s": 2.0,
  "phone_s": 1.0,
  "detectors": {"drowsiness": true, "distraction": true, "phone": true, "physiology": true}
}
```

`PUT` takes any subset (`detectors` merges key by key) and answers with the full object. These are
**Pi-side** settings: fusion (and the models' on/off switches) use them. The app only edits them;
it does not apply them. `profile` selects the drowsiness calibration profile (`--face-profile`,
`profiles/` on the Pi).

App-only settings (language, theme, units, voice volume, vibration, crash detection, emergency
contacts) stay on the phone.

## `POST /test_alert` (proposed)

Body `{"pattern": "max"}`. The Pi sounds that buzzer pattern and reports it on `/alert` for ~3 s
(`reasons: ["test alert"]`), so one tap exercises buzzer + `/alert` + the phone's alert engine.
400 for an unknown pattern.

## `GET /health` (proposed)

```json
{
  "cpu_pct": 61.2, "temp_c": 66.1, "throttled": 0, "volts_5v": 5.08, "fps": 14.6,
  "uptime_s": 3725, "mem_used_mb": 2140, "mem_total_mb": 8064,
  "disk_free_mb": 41210, "disk_total_mb": 58940, "camera": "ok",
  "models": {"face": "running", "distraction": "running", "physiology": "running", "fusion": "running"}
}
```

`throttled` is the raw `vcgencmd get_throttled` bitmask; the app decodes bits 0–3 (now) and 16–19
(since boot). `volts_5v` from `vcgencmd pmic_read_adc EXT5V_V`. `models.*` ∈ `running | off | error`.
Polled once a second only while the Pi tab is on screen.

## `POST /incident` (proposed)

Body, sent by the phone the moment it detects a crash (or on manual SOS):

```json
{"t_crash": 1732117202400, "g_peak": 6.4, "lat": 31.20012, "lon": 29.91871}
```

`t_crash` is the phone's wall clock in **ms**; the Pi maps it onto its ring buffer (20 s kept
because this request arrives late over Wi-Fi). Response `{"id": "2026-11-20T15-40-02-400Z"}`.
The Pi writes `incidents/<id>/clip.avi` at once, then `clip.mp4` (ffmpeg, low priority),
`data.jsonl`, `meta.json`.

## `GET /incidents` (proposed)

```json
[{"id": "2026-11-20T15-40-02-400Z", "t_crash": 1732117202400, "g_peak": 6.4, "lat": 31.2, "lon": 29.92, "duration_s": 25, "clip_ready": true}]
```

`clip_ready` stays `false` until `clip.mp4` exists.

## `GET /incidents/<id>/clip.mp4` (proposed)

H.264 MP4 (phones cannot play MJPEG AVI), 25 s: 15 s before + 10 s after `t_crash`. The app
streams it in `expo-video` and can save it under the app's documents folder.

## `GET /incidents/<id>/data.jsonl` (added by the app)

Not in the spec's table, needed to draw the sensor timeline under the clip. One line per buffered
frame (10 fps), the same `/status` object the ring buffer stored, plus the `/alert` at that moment:

```json
{"t": 1732117187400, "status": { "...": "a /status object" }, "alert": {"pattern": "repeated", "reasons": ["face drowsy"], "t": 1732117187.4}}
```

## `POST /system/restart`, `POST /system/shutdown` (proposed)

No body, `{"ok": true}`. Restart = the monitoring service (systemd unit), not the whole Pi.
The app asks for a native confirmation first.

## Pairing QR code

A standard Wi-Fi QR with one extra field, so any phone camera can still join the hotspot:

```
WIFI:T:WPA;S:RTDMS-Pi;P:<password>;U:http://10.42.0.1:8080;;
```

`U:` (base URL) is optional; without it the app uses `http://10.42.0.1:8080`. A bare
`http://host:port` QR also works (mock Pi on a laptop). Special characters in fields are escaped
with `\` as in the Wi-Fi QR format. Parser + tests: `parseQr` in `src/pi/parse.ts`.
On Android the app joins with `WifiNetworkSpecifier` and binds its process to that network
(`sahi-native` `joinWifi`), because the hotspot has no internet and Android would otherwise send
requests for `10.42.0.1` over mobile data.
