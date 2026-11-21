# Pi ↔ phone link contract (version 1)

Single source of truth for the Sahi app (`app/`) and the Pi runtime (`pi/`). Design rationale:
`Subsystems/Phone-Pi Link.md`. **Owner: the coordinator.** Neither side edits this directory
directly: propose a change as a CR on the coordination board (`~/RTDMS-coord/BOARD.md`), wait for
the other side's ACK, and the coordinator merges it and bumps the version below.

Payloads are compact JSON (UTF-8, no whitespace). Schemas: `schemas/<name>.schema.json`. Golden
examples: `fixtures/<name>.json`. `validate.py` checks every fixture against its schema and the
notify size budget; both sides must also validate their own fixtures in their own test suites.
Field names match `app/src/pi/types.ts` where a field already existed.

## Transport split

| Link | Carries | Used |
|---|---|---|
| **BLE** (Pi = GATT peripheral, phone = central) | everything in the table below | whole trip |
| **Wi-Fi** (Pi = access point, no internet, HTTP on port 8080) | `/stream.mjpg`, `/incidents*` clip and data | only while Live / Calibrate is open or a clip downloads |

BLE is the control and safety path. The phone must be able to arm crash detection, receive alerts
and send `incident` without Wi-Fi ever being up. For a video session the phone simply joins the
Pi's access point using the credentials from the pairing QR; no BLE command is needed for that.

## GATT layout

> [!warning] One service only
> `models/physiology/src/dms_physiology/garmin_receiver.py` documents that `bless` 0.2.6
> advertised the first service and **dropped a second service** from the GATT table (2026-11-08),
> and the Garmin watch needs the advertised 16-bit UUID. Therefore all phone characteristics live
> in the **existing service** `0000fff0-0000-1000-8000-00805f9b34fb`, next to the Garmin RR
> characteristic `1375193a-7edb-4a34-b3f2-18130239c8a8`. If the Pi's spike (P1) shows two services
> work, a CR may split them. Until then: one service.

Phone characteristics: base `1375193a-7edb-4a34-b3f2-1813023900NN` (NN below). Names and sizes:

| NN | Name | Properties | Payload schema | Rate / rule |
|---|---|---|---|---|
| 01 | `alert` | notify, read | `alert` | on every change and a 5 Hz keep-alive; **only input to the phone's alert output** |
| 02 | `status` | notify, read | `status` | 2 Hz; the slimmed `/status` |
| 03 | `physio` | notify, read | `physio` | 1 Hz |
| 04 | `settings` | read, write | `settings` | write takes any subset; read returns the full object |
| 05 | `command` | write | `command` | result comes back on `result` |
| 06 | `result` | notify | `command_result` / `incident_response` | one notify per `command` or `incident` write |
| 07 | `incident` | write | `incident_request` | phone writes on crash or manual SOS; result on `result` |
| 08 | `clock` | write | `clock` | phone writes its wall clock (ms) on every connect |
| 09 | `auth` | write | `auth` | first write after connecting; all other writes are rejected until accepted |
| 0a | `health` | read | `health` | long read (≤ 512 B) |

Rules:
- Notify payloads (`alert`, `status`, `physio`) stay ≤ **240 bytes** (MTU 247 − 3 B header,
  with margin). The phone requests MTU 247 on connect and falls back to the default MTU with the
  same payloads if refused (the budget above still fits: the Pi truncates `reasons` first).
- Unknown JSON fields are ignored on read (forward compatibility). Missing required fields mean
  the payload is dropped, never guessed (existing app rule: parse failures give `null`).
- All write characteristics use write-with-response. The Pi answers a rejected write with an
  ATT error (insufficient authentication) until `auth` succeeds.
- The Pi keeps advertising after a phone disconnects. The phone reconnects by remembered address.
- **Garmin first:** the Pi runtime must not delay the Garmin RR stream for phone traffic. The Pi
  rate-limits phone notifies if the Garmin loss rate rises (budget gate in P6).

## Pairing

The QR (schema `qr`, encoded as the standard Wi-Fi QR with extra fields):

```
WIFI:T:WPA;S:<ssid>;P:<psk>;U:<url>;B:<ble name>;K:<token>;V:1;;
```

- `K` is a random token (≥ 16 chars) generated on the Pi at first start, stored on the Pi only,
  shown as a QR on the Pi's setup page or printed by a CLI. The phone writes it to `auth` after
  connecting. Rotating it unpairs every phone.
- The phone saves ssid, psk, url, BLE name/address and token in secure storage.
- `V` is the contract version. If `health.contract` ≠ the app's version, the app shows a
  "Pi software mismatch" state and keeps only what is compatible (never guesses).

## Capabilities (replaces HTTP 404 feature hiding)

The `health` payload's `models` map says which parts run. The app hides a feature when the
matching key is absent or `off`/`error`. It no longer infers support from `404`s.

## Incident flow

1. Phone detects a crash (or manual SOS) and writes `incident` with `t_crash` (phone wall clock,
   ms), `g_peak`, location and a `client_id` (UUID, makes retries idempotent).
2. The Pi maps `t_crash` onto its ring buffer using the offset from the latest `clock` write
   (offset = Pi time at write − `phone_ms`), keeps ≥ 20 s, and answers on `result` with the
   incident id. A repeated `client_id` returns the same id.
3. The phone keeps retrying the `incident` write (with backoff) until it gets a `result`, and
   falls back to HTTP `POST /incident` if Wi-Fi is up. **Crash detection and SMS/call never wait
   on any of this** (they use the phone's own sensors and cellular).
4. Wi-Fi session: `GET /incidents` (list of `incident_item`), `GET /incidents/<id>/clip.mp4`,
   `GET /incidents/<id>/data.jsonl`, `GET /incidents/<id>/meta.json`. `clip_ready` is false until
   `clip.mp4` exists.

## HTTP (Wi-Fi) endpoints that remain

| Method | Path | Notes |
|---|---|---|
| GET | `/stream.mjpg` | unchanged (`models/distraction/scripts/stream.py`): MJPEG, ~640 px, q70, ≤ 10 fps, encodes only while a viewer is connected |
| GET | `/incidents`, `/incidents/<id>/{clip.mp4,data.jsonl,meta.json}` | as above |
| POST | `/incident` | same body as `incident_request`, response `incident_response`; BLE fallback only |

HTTP requests carry the token as `Authorization: Bearer <token>`. `GET /status`, `/alert`,
`/physio`, `/health`, `/settings`, `/test_alert`, `/calibrate`, `/system/*` from
`app/docs/API.md` remain available on Wi-Fi for debugging and the mock Pi, with the same
payloads as their BLE counterparts, but the app uses BLE for them once the BLE transport lands.

## Version history

| Version | Date | Change |
|---|---|---|
| 1 | 2026-11-21 | First version |

## Open questions for the spike (P1) and first integration

1. Does `bless` on the Pi's BlueZ 5.82 keep the Garmin characteristic and the ten phone
   characteristics working in one service, with the watch and a phone connected at once?
2. What MTU and connection interval does Android grant in practice? (`status` payload size
   assumes 247.)
3. Does the Wi-Fi access point on 5 GHz leave the Garmin loss rate unchanged?

Results go into `Subsystems/Phone-Pi Link.md` (Results). A failed question opens a CR.
