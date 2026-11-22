---
title: "Dev Environment and Test Devices"
tags:
  - setup
  - dev
  - devices
status: current
updated: 2026-11-22
---

# Dev Environment and Test Devices

↑ [[Home]] | [[Project Log 2026-11]] | Pi device facts: [[Raspberry Pi 5 Target]] | Relay: [[WhatsApp SOS Relay]]

How to run and test everything we have, from the dev machine (Linux, Node 24, Docker). **No
passwords or API keys are written here.** Secrets live in `~/RTDMS-coord/relay-data/` (outside git,
mode 0700), `~/RTDMS-coord/secrets/pi.env` (Pi user and sudo password, mode 0600) and in the
gitignored `app/.env.local`.

## Test devices

| Device | Details | Notes |
|---|---|---|
| **realme GT 6T** (RMX3853) | Android 16 (API 36), ColorOS, 1264×2780, Google Play services present, Tailscale installed | Primary test phone. SMS permission is blocked for a sideloaded APK until "Allow restricted settings" is chosen (Settings → Apps → Sahi → ⋮). Keep it charging: it ran at 31–36% |
| HUAWEI FRL-L22 | Android 10 (API 29), EMUI 10.1, **no Google Play services** (HMS only) | Was tried first and replaced. Keep the Android 10 and no-GMS code paths working |
| Raspberry Pi 5 | Debian 13 (trixie), `eth0` + Tailscale, `wlan0` down. Linger on (user services start at boot). Camera ribbon detached on purpose (22 Nov), so `rtdms-camera` is stopped | **Tailscale is the normal route:** `ssh khalifa@100.113.107.122` (key auth). Sudo password in `~/RTDMS-coord/secrets/pi.env`. See [[Raspberry Pi 5 Target]] and "Pi on a direct cable" below |

## Network picture

```text
realme phone (Tailscale) ──► dev machine 100.86.213.114
                               ├─ Metro dev server     :8081  (loads the app JS)
                               └─ SOS relay            :8088  (WhatsApp via Baileys)
realme phone (Tailscale) ──► Pi 100.113.107.122:8080          (camera server: /status, /stream.mjpg)
```

All Tailscale links are relayed (not direct), so the round trip is slow and uneven (18–366 ms
measured once). Use them for functional tests, **never for latency numbers**.

### Pi on a direct cable (when it has no Wi-Fi)

Set up on 22 Nov when the Pi was cabled straight into the dev machine's `eno1`:

- **Find it** without an IPv4 address: `ping -6 -c2 -I eno1 ff02::1`, then
  `ssh 'khalifa@fe80::<addr>%eno1'` (Raspberry Pi MACs start `2c:cf:67`).
- **Pi side (persistent):** NetworkManager "Wired connection 1" is static `10.77.0.2/24`, gateway
  `10.77.0.1`, DNS 1.1.1.1 / 8.8.8.8.
- **Dev machine side (lost on reboot):** `sudo ip addr add 10.77.0.1/24 dev eno1`, a MASQUERADE rule
  for `10.77.0.0/24` out of `wlo1`, and two FORWARD accepts (`eno1 → wlo1`, and established
  traffic back). With internet the Pi rejoins Tailscale, and everything else goes over Tailscale as usual.

## Build and run the app

1. **Build (cloud, no local Android SDK):** from `app/` run `npm ci`, then
   `npx eas-cli build --profile development --platform android --non-interactive`. The Expo project
   is `@teamaziad/sahi`. The first upload was 290 MB because screenshots are included.
   A new build is needed only when native code or permissions change (the SMS delivery-report
   change, the future Bluetooth plugin). JavaScript changes do not need one.
2. **Install:** `adb -s <serial> install -r sahi-dev.apk` (the phone must be in "Transfer files" mode
   with USB debugging on; Huawei needs "Allow HiSuite to use HDB" off).
3. **Serve the JavaScript:** from `app/`, `CI=1 REACT_NATIVE_PACKAGER_HOSTNAME=<dev machine Tailscale IP> npx expo start --dev-client --port 8081 --host lan --clear`.
4. **Open on the phone:** enter `http://<dev machine Tailscale IP>:8081` in the dev client, or over USB
   `adb reverse tcp:8081 tcp:8081` and open `sahi://expo-development-client/?url=http%3A%2F%2Flocalhost%3A8081`.
   The USB forward disappears whenever the server restarts: re-run it.
5. **Connect to the Pi:** pair with `http://100.113.107.122:8080` (Diagnostics has the address field).

## Run the WhatsApp relay

1. `cd relay && npm ci`, then load the env file (`RELAY_API_KEY`, `PORT=8088`, `RELAY_DB_PATH`,
   `RELAY_AUTH_DIR` pointing into `~/RTDMS-coord/relay-data/`) and `npm start`.
2. First run only: the relay prints a pairing QR. Link a **dedicated spare WhatsApp number**
   (Settings → Linked devices → Link a device). Health then shows `whatsapp: connected`.
3. **Smoke test** (sends real WhatsApp messages to one number, then deletes the registration):
   register the number, wait for the opt-in, `POST /v1/sos`, poll `GET /v1/sos/{client_id}` until
   `delivered`. Use only your own number.
4. The session files are the WhatsApp account: keep them private; deleting them unlinks the number.

## Gates (run these yourself; never trust a delegate's "done")

| Zone | Command |
|---|---|
| `app/` | `npx tsc --noEmit && npx eslint . && npx jest` (+ `npx expo-doctor`, the design-token grep in `app/docs/VALIDATION.md`) |
| `pi/` | `cd pi && docker compose run --rm verify` (pytest, ruff, mypy --strict) |
| `relay/` | `npx tsc --noEmit && npx eslint . && npx vitest run` |
| `contracts/` | `python3 contracts/pi-link/validate.py` (needs `jsonschema`) |
| `fusion/` | `cd fusion && PYTHONPATH=src pytest` |

## Gotchas learned the hard way

- `pkill -f "expo start"` **kills your own shell** if the command line contains the same words. Put long-running starts in a script file and match with a bracket pattern (`pgrep -f '[e]xpo start'`).
- Metro in `CI=1` mode has no live reload; restart it after changing `.env.local`.
- Screenshots of the phone can capture personal notifications: turn on Do Not Disturb and never commit device screenshots unchecked.
- Codex has a usage quota (it ran out on 22 Nov, back at 23:01); agy was the only implementer meanwhile.
- A passing **dry-run** smoke test does not prove the real transport starts (see the `npm start` bug in [[Project Log 2026-11]]).
