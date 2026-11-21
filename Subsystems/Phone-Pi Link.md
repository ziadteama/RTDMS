---
title: "Phone–Pi Link — how Sahi talks to the Pi"
tags:
  - subsystem
  - app
  - mobile
  - connectivity
  - research
  - decisions
aliases:
  - Phone-Pi Link
  - Sahi transport
  - phone Pi communication
status: proposed
researched: 2026-11-21
---

# Phone–Pi Link — how Sahi talks to the Pi

↑ [[Home]] | Related: [[Competitor App Study]] | Raspberry Pi device facts: [[Raspberry Pi 5 Target]] | Pi config research: [[Pi Setup Plan]] | Physiology BLE: [[Physiology Subsystem]]

Research-backed decision on the link between the Sahi phone app (see **Mobile App**, branch
`docs/mobile-app`; code on `app/*` branches) and the Raspberry Pi. Written **2026-11-21**.

> [!abstract] Decision (proposed, pending the bench spike)
> **Hybrid: BLE always on for alerts, heart data, settings and the crash trigger; the Pi's Wi-Fi
> hotspot only for live video and clip downloads.** The app today is Wi-Fi/HTTP only. Nothing here
> is built yet and **nothing has been measured**: the choice is reasoned from research and from the
> repo as it stands, and the spike in [[#Bench spike]] decides go / no-go.

## What the app does today

Source: `app/docs/API.md` and the app code on `origin/app/crash-sos-trips`.

- The Pi runs a hotspot (`RTDMS-Pi`, `10.42.0.1:8080`, no internet). The phone joins from a QR code
  with `WifiNetworkSpecifier` and `bindProcessToNetwork` (Android only, `modules/sahi-native/`).
- Transport is plain HTTP + JSON polling: `/status` + `/alert` at ~5 Hz, `/physio` at 1 Hz, offline
  after 3 failed `/status` calls. Video is `/stream.mjpg` in a WebView. There is a clean
  `PiTransport` interface (`app/src/pi/transport.ts`) with HTTP and demo implementations.
- **No BLE code and no BLE library** in the app. Native module is Android-only.
- Only 3 of 14 endpoints exist on the Pi (`/stream.mjpg`, `/status`, `/calibrate`, in
  `models/distraction/scripts/stream.py`, stdlib `ThreadingHTTPServer`, no auth).

### Weak points found in the app's design

| Finding | Where | Why it matters |
|---|---|---|
| **Automatic crash SOS needs the Pi link** | `services/monitor.ts` arms the detector only while `online` | A dropped hotspot silently disables crash detection. SMS/calls themselves use cellular and do not need the Pi. |
| `POST /incident` sent once, 4 s timeout, no retry or queue | `services/emergency.ts` | A flaky link loses the clip association (`piId: null`). |
| Process stays bound to the no-internet network | `joinWifi` binds; `unbindNetwork` has no caller | Other app traffic can go nowhere until the network is lost. |
| iOS config missing | `app.json` has no ATS exception, no local-network text, no background modes | Plain HTTP to the Pi would likely be blocked on iOS. Android-only is the decision for now. |
| Pi-side endpoints (`/alert`, `/physio`, …, incidents) | not built | See [[#What is left to build on the Pi]]. |

## Facts about the Pi side

Source: repo scan, 2026-11-21.

- **The Pi is already a BLE peripheral** for the Garmin watch:
  `models/physiology/src/dms_physiology/garmin_receiver.py` runs a `bless` GATT server (service
  `0xFFF0`, `bless>=0.2.6,<0.3`) and the watch connects as central. A phone would be a **second
  central on the same peripheral**, not a dual-role setup (the risky case in the research).
- Classic Bluetooth is disabled (`setup_bluetooth_le.sh`: `ControllerMode=le`, 100–150 ms
  advertising). BlueZ 5.82. `wlan0` is down today. No systemd units, hotspot or NetworkManager
  config exist in the repo.
- Garmin link results so far: first session 2026-11-08, 0 loss at ~1 packet/s. **Pi↔wearable latency
  (<100 ms target) is not measured anywhere.** No Wi-Fi/BT coexistence notes.
- `stream.py` encodes MJPEG only while a viewer is connected: 640 px, JPEG q70, ≤10 fps. Face-only
  Pi run (2026-10-10): 30 fps camera-bound, ~21% CPU, 48–51 °C. **Concurrent three-model numbers
  and the 30-minute soak are not measured.**
- `fusion/` is a `decide()` stub (`AlertPattern`: none, short_beep, repeated, continuous, max).
  No transport and no GPIO. `stream.py` does not call `decide()`.
- Pi access for tests: LAN `192.168.100.181`, user `khalifa`, key `~/.ssh/id_ed25519`
  (Tailscale SSH needs check mode). See [[Raspberry Pi 5 Target]] and [[Agent Guide]] §5.

## What is left to build on the Pi

Of the 14 endpoints in the app's API contract only the 3 above exist on the Pi.

1. `GET /alert`: latest `decide()` result. Needs fusion running in the live process.
2. `GET /physio`: watch state, HR, RR, fatigue probability, HRV snapshot.
3. `GET/PUT /settings`, `POST /test_alert` (buzzer GPIO still pending).
4. `GET /health`, `POST /system/restart|shutdown` (needs a systemd unit first).
5. Incident recording (largest piece): 20 s ring buffer, `POST /incident`, ffmpeg H.264 clip,
   `data.jsonl`, `meta.json`, `GET /incidents…`.
6. Pi networking: hotspot and the pairing QR.

If BLE carries alerts, items 1–4 and the incident trigger become GATT characteristics. Items
5 and the video stay on HTTP.

## Requirements this has to satisfy

- End-to-end alert latency **<500 ms**; Pi↔wearable Bluetooth trigger **<100 ms**
  ([[3.2 Technical Description]]).
- Local/edge only, no cloud, no permanent biometric storage ([[4.3 Ethics]] 4.3.1.1: "No personal or
  biometric data is stored permanently or transmitted over external networks such as Wi-Fi or
  Bluetooth").
- Phase 2: alerts within 1 s, emergency escalation by GPS ([[5.2 Phase Two Plan]]).

> [!warning] Privacy wording tension
> 4.3.1.1 says nothing is transmitted over Wi-Fi or Bluetooth, but the design already uses a local
> Bluetooth link to the watch and a local LAN page. A local-only phone link (no internet, no
> cloud) is consistent with the intent, but the report wording should be adjusted. `stream.py`
> also serves live video to any LAN host with no auth; the physiology receiver writes raw heart
> data to CSV by default (flagged in [[Physiology Decision Log]]).

## Options compared

| Option | Verdict |
|---|---|
| **Wi-Fi hotspot + HTTP only** (current) | Simplest, proven by dashcams, but the alert and crash path depends on the most fragile leg (Android no-internet Wi-Fi). |
| **BLE only** | ~100 kB/s practical ceiling, too slow for live video and ~25 s clips. |
| **Hybrid: BLE + Wi-Fi hotspot** | **Recommended.** Safety data on BLE; bulk data on Wi-Fi only when needed. |
| Phone hotspot, Pi as client | The user must switch it on every trip, the Pi's address changes and needs discovery, and the phone has to share its connection. |
| **Bluetooth tethering (PAN)** | Rejected as the main link: apps cannot switch it on; ~1–2 Mbps is too slow for 640 px MJPEG at 10 fps; it needs Classic Bluetooth, which is off and shares the controller with the Garmin link; and it would give the Pi internet through the phone, against the local-only rule. Possible fallback for a low-res preview. |
| Wi-Fi Direct, USB | Not researched; no evidence either helps. |
| Cloud / LTE (fleet products) | Ruled out by the privacy requirement. |
| iOS | Out of scope: silent SMS and calls need Android, and iOS no-internet Wi-Fi is fragile (see below). |

## How dashcams do it (reference pattern)

Sources are manuals and support pages; vendor behaviors not verified on a device are marked.

| Product | Control / pairing | Live view and clips | Crash handling |
|---|---|---|---|
| Garmin Dash Cam | Bluetooth and Wi-Fi ([manual](https://www8.garmin.com/manuals/webhelp/GUID-41AB4C2D-E75E-460B-A06B-930BF002AAB8/EN-US/GUID-6A04F006-EBD6-4BBA-8ADA-79148ADF0743.html)) | Wi-Fi; AP or the camera joins a Wi-Fi network | Camera detects; where it has LTE it texts emergency contacts ([Incident Detection](https://www8.garmin.com/manuals/webhelp/driveassist51/EN-US/GUID-D172B6AF-7FB8-4242-9B96-52ADB6F15B4F.html)) |
| Nextbase | Bluetooth pairing, then a Wi-Fi join prompt ([article](https://support.nextbase.com/en/articles/617023-how-to-connect-to-the-mynextbase-connect-app)) | Wi-Fi | Subscription Emergency SOS: camera detects high-G, phone sends the request, calls contact then emergency services ([article](https://support.nextbase.com/en/articles/612208-emergency-sos)) |
| BlackVue | Wi-Fi Direct; newer "Seamless Pairing" joins in-app | Direct Wi-Fi; cloud over the camera's LTE | G-sensor files on camera; phone SOS unverified |
| Thinkware | BLE on newer models, else manual join (secondary sources) | Wi-Fi; AP times out after 2 min with no client | unverified |
| 70mai | Camera hotspot, prompt-driven ([guide](https://70mai.store/cdn/shop/files/70mai-DashCam-App-Connection-Guide.pdf)); BLE only on some models | Wi-Fi | unverified |
| Viofo | Join the camera Wi-Fi manually, then open the app ([guide](https://www.viofo.com/blogs/viofo-car-dash-camera-guide-faq-and-news/how-to-connect-the-viofo-app-and-what-to-do-if-the-connection-fails)) | Wi-Fi | unverified |
| Fleet (Samsara, Motive, Lytx, Netradyne) | No phone; on-device LTE to the cloud ([Samsara](https://www.samsara.com/fleet/dash-cam)) | Cloud | Camera and gateway |

**The general pattern:**
1. Consumer cameras are cloud-free: the camera is a Wi-Fi AP with no internet.
2. BLE, where present, only does pairing and auto-reconnect. Wi-Fi carries all bulk data.
3. Auto-joining the camera Wi-Fi from the app is the exception; mostly it is manual or prompt-driven.
4. Crash detection lives **on the camera** (G-sensor). Phone-side SOS is an optional add-on.
5. Fleet products skip the phone and use LTE: ruled out here by privacy.

**Where we differ on purpose:** a dashcam's phone is a passive viewer; Sahi's phone is an active
safety output (voice, haptics, SOS), so its data must not depend on the fragile Wi-Fi leg.
Our Pi also has no accelerometer, which is why the phone triggers the incident today. An I2C IMU
(for example MPU-6050) on the Pi would let it lock the clip itself, as dashcams do. This is a
follow-up idea, not part of this scope.

### Pitfalls the vendors document

- Android Smart Network Switch / Adaptive Connectivity / "Switch to mobile data" drops a no-internet
  Wi-Fi network (BlackVue); iOS has Wi-Fi Assist.
- Wireless Android Auto or CarPlay holds the phone's Wi-Fi and blocks the camera link (Viofo,
  Nextbase, 70mai).
- Battery optimisation, VPNs and missing Nearby Devices / Location / Local Network permissions break
  pairing. Nextbase advises turning off mobile data while pairing.
- Maps and other online content are unavailable while the phone is on the camera's Wi-Fi.
- The camera AP shuts off when no client connects (Thinkware, 2 min).
- Garmin needs a network without client isolation.

## Research findings: Android, iOS, Pi

Sources are in-line. Items marked *unverified* are inference or have no source and need a device test.

### Android and a no-internet Wi-Fi network

- `WifiNetworkSpecifier` gives a local-only connection without internet
  ([Android docs](https://developer.android.com/develop/connectivity/wifi/wifi-bootstrap)).
- The first approval is remembered per app and access point. A later request for the **same SSID or
  BSSID** skips the dialog. An SSID or BSSID *pattern* always prompts. Use an exact SSID.
- The connection lasts only while the app's request callback is registered. Behavior when the app
  is backgrounded or killed, Samsung/Xiaomi differences, and `bindProcessToNetwork` caveats were
  *not found in sources*: test on devices. Cellular (calls, SMS) is a separate transport and should
  stay up.
- `WifiNetworkSuggestion` persists and auto-connects, but asks the user on first use (Android 11+),
  is ignored if the user manually disconnects while in range, and may not outrank a saved internet
  network (*unverified*) ([docs](https://developer.android.com/develop/connectivity/wifi/wifi-suggest)).

### iOS (for the record; not the target)

- `NEHotspotConfiguration` with `joinOnce = true` ends with the app. Forum reports show no-internet
  hotspots dropping after 15–20 s on iOS 13 (fixed with `joinOnce = false`), dropping on the first
  connection after a reboot on iOS 18.3, and iOS switching away from an accessory network to a saved
  internet network on iOS 26. These are anecdotal threads
  ([122540](https://developer.apple.com/forums/thread/122540),
  [774340](https://developer.apple.com/forums/thread/774340),
  [848895](https://developer.apple.com/forums/thread/848895)).

### Pi 5 Wi-Fi AP and Bluetooth

- Wi-Fi and Bluetooth share one chip (CYW43455, same as Pi 4). BLE packet loss while Wi-Fi is active
  is reported on that and similar chips
  ([Infineon](https://community.infineon.com/t5/Wi-Fi-Bluetooth-for-Linux/CYW43455-seems-losing-BLE-packets/m-p/51795)).
  **No measured data for a Pi 5 as AP plus BLE was found.**
- The BCM43455 firmware crashes with concurrent station + AP mode on Raspberry Pi OS Trixie;
  Bookworm avoids it ([linux#7092](https://github.com/raspberrypi/linux/issues/7092), issue number
  not confirmed from the page itself). We need AP only, but test on the Pi's actual OS.
- A NetworkManager hotspot was invisible on Ubuntu 24.04 but fine on Bookworm
  ([Launchpad 2065828](https://bugs.launchpad.net/ubuntu/+source/network-manager/+bug/2065828)).
- Mitigation to test: 5 GHz with a fixed non-DFS channel (36–48) keeps the AP off BLE's 2.4 GHz band;
  set the regulatory domain. Range inside a car is not an issue.

### BLE peripheral serving two centrals

- Reports of connection timeouts when one adapter did both roles (central and peripheral) are old
  (BlueZ 5.50, 2017–18) and concern dual-role, not two centrals
  ([linux-bluetooth](https://lore.kernel.org/linux-bluetooth/9390ebceb54942d9999693bb0ff08949@fronius.com/T/),
  [Qt QTBUG-67416](https://bugreports-test.qt.io/browse/QTBUG-67416)). Nothing was found on `bless`
  specifically. Needs a bench test.
- Practical BLE throughput is about 100–125 kB/s, mostly set by the connection interval the phone
  grants, not by the MTU ([Nordic](https://devzone.nordicsemi.com/f/nordic-q-a/32585/nrf52832-sdk-14-0-s132-5-0-0-optimizing-ble-throughput-between-nrf52-peripheral-and-android-device-central)).
  5 Hz alerts of a few hundred bytes fit easily; video and clips do not.
- `react-native-ble-plx` exposes MTU only. PHY and connection priority need native code
  ([thread](https://devzone.nordicsemi.com/f/nordic-q-a/32449/improve-ble-throughput-in-react-native-ble-plx-mobile-app)).
  Android background BLE, reconnect behavior and ble-plx on Expo dev builds were *not researched*.

### Push transport in React Native (if staying on Wi-Fi)

- React Native's default `fetch` does not stream. `expo/fetch` (SDK 52+) does, and
  `react-native-sse` gives an EventSource ([Expo SDK 52](https://expo.dev/changelog/2024-11-12-sdk-52),
  [npm](https://www.npmjs.com/package/react-native-sse)). So polling is not required.
  WebSocket reliability in React Native was *not researched*.

### Video on the Pi 5

- The Pi 5 has **no hardware H.264 encoder**: software x264 on the CPU, which competes with the
  vision models. 1080p30 is possible, but not below ~240 kb/s
  ([Raspberry Pi white paper RP-010033](https://pip-assets.raspberrypi.com/categories/685-app-notes-guides-whitepapers/documents/RP-010033-WP-1-H.264%20encoding%20performance%20on%20Raspberry%20Pi%205_series%20computers.pdf),
  CPU numbers not read). Low-res, low-fps MJPEG (current) is the cheap preview. That is an
  inference. WebRTC was not researched.

## Recommended design

| Link | Carries | When |
|---|---|---|
| **BLE** (Pi GATT peripheral, phone central) | alert (notify), slim status, physio (1 Hz notify), settings, test alert, health, **incident trigger (write with response)**, clock sync | The whole trip |
| **Wi-Fi hotspot** (Pi AP, 5 GHz fixed channel, exact SSID) | `/stream.mjpg`, calibration view, clip and data download | Only while Live/Calibrate is open or a clip downloads; released afterwards |

Also:
- **Crash detection runs on the phone alone** (motion + GPS speed); the Pi link only adds evidence.
  This removes the `online` gate in `monitor.ts`.
- **Incident trigger uses a retry queue**: BLE first, Wi-Fi as fallback.
- **One pairing QR** carries Wi-Fi credentials, the BLE identity and an auth token. The Pi accepts
  commands only after the token is written.
- **Pi clock**: the Pi has no internet, so the phone sends its wall clock on connect (needed to
  map `t_crash` onto the ring buffer).
- **Fallbacks:** if phone + watch on one radio fails, use Wi-Fi only with push (SSE or WebSocket)
  instead of polling and document the Android Auto conflict. If the hotspot fails under load, use
  BLE only and move video to post-trip download.

Later app changes this implies (not built here): `BleTransport` behind `PiTransport`;
`react-native-ble-plx` with Android 12+ BLUETOOTH_SCAN/CONNECT permissions; unbind after a video
session; incident retry queue; onboarding that checks the dashcam pitfalls above.

## Bench spike

**Goal:** go / no-go on the hybrid. **Status: not run.** Results go in [[#Results]] as measured
numbers; nothing is to be filled in from expectation.

Tooling (to be created under `models/physiology/tools/pi/link_spike/`, off the runtime path, on a
`physio/` branch because it extends the bless receiver): a GATT spike adding an `alert` notify
characteristic (~60 B at 5 Hz), a `ping` echo and an `incident` write-with-response; a `bleak`
laptop client as a stand-in phone; nRF Connect on a real Android phone for MTU, screen-off
notifications and reconnect. Hotspot: `nmcli` AP on 5 GHz, fixed non-DFS channel; fall back to
2.4 GHz only if a test phone will not join. Also check Smart Network Switch on and off, and
wireless Android Auto if a car with it is available.

| Run | Load (each ≥10 min; D is a 30 min soak) |
|---|---|
| A | Watch only: baseline Garmin loss |
| B | Watch + BLE spike client |
| C | B + hotspot + 1 MJPEG viewer |
| D | C + full `start_stream.sh` pipeline |

Record: Garmin packet loss, BLE round-trip p50/p95, notify loss, reconnect time, `stream.py` fps
(`/status`), MJPEG fps on the phone, CPU, temperature, `vcgencmd get_throttled`, and any `dmesg`
brcmfmac or Bluetooth errors.

**Go criteria:** Garmin loss in B/C/D no worse than A · BLE round-trip p95 under 100 ms · reconnect
under 5 s · no firmware or BT crash in the soak · `stream.py` fps down 10% or less with the hotspot
and one viewer.

### Results

*Not run yet. The Pi was offline on 2026-11-21.*

**Tooling status (2026-11-21):** the spike tools were written under `pi/tools/link_spike/` (not
`models/physiology/tools/pi/link_spike/` as planned: the real phone service in [[Pi Runtime]] uses
the contract's characteristics, so the spike measures the real service). Written and unit-tested
for their pure parts; **never run on hardware**. Run order and go criteria are unchanged above.

### Pi-side implementation status (not verified on hardware)

The phone service, auth gate, notifier rates and incident store are implemented and tested in
Docker with a simulated GATT layer (one Bluetooth adapter cannot loop back to itself, so a bleak
loopback on the dev machine was not possible). Open items for the spike: `bless` has no
disconnect event (auth uses a TTL), ATT error mapping for rejected writes, one service holding 11
characteristics with the watch connected. Details: [[Pi Runtime]].

## Open questions

- Does the second BLE central coexist with the Garmin link under `bless` and BlueZ 5.82?
- Does a Pi 5 AP on 5 GHz stay up next to BLE under full pipeline load, on the OS actually deployed?
- Android: does the specifier link survive screen-off, backgrounding and vendor battery managers
  (Samsung, Xiaomi)? Can `bindProcessToNetwork` be released safely after a video session?
- Where is the in-car Wi-Fi/BLE antenna placement problem (metal enclosure, dash mount)? Not
  researched.
- Report wording (4.3.1.1) versus a local phone link.
- Whether to add an IMU on the Pi so crash clips are locked without the phone.
