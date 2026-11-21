---
title: "Competitor App Study — what established apps teach Sahi"
tags:
  - subsystem
  - app
  - mobile
  - research
  - competitors
aliases:
  - Sahi competitor study
  - app study
status: research
researched: 2026-11-21
---

# Competitor App Study — what established apps teach Sahi

↑ [[Home]] | Link design: [[Phone-Pi Link]] | Business benchmarks: the commercial DMS set in `CLAUDE.md` and the report §4.2.2

Study of apps near Sahi: **dashcam companion apps**, **driver-monitoring / fleet apps**, and
**crash-detection / trip-scoring apps**. Written **2026-11-21** from web research by three
research agents, structured with the `competitive-brief` skill's layout (its marketing-messaging
parts were not used).

> [!warning] How far to trust this
> Evidence is **search results, vendor pages, manuals and aggregator snippets**. Play Store and
> Reddit review text was mostly not reachable, so complaint frequencies are **qualitative**.
> Ratings come from aggregators and vendor pages. Claims marked *unverified* are vendor claims or
> single anecdotes. Nothing here was tried on a device. Several vendor pages contradict each other
> (noted below).

> [!abstract] Bottom line
> 1. **Nobody does what Sahi does.** No app combines driver-state alerts, calibration, watch heart
>    rate, a crash SOS and a trip score for a personal vehicle with local-only data. Fleet products
>    are manager-centric and cloud-based; dashcam apps are viewers.
> 2. **The top complaint everywhere is the connection**, not features. Sahi's in-app Wi-Fi join and
>    the BLE hybrid in [[Phone-Pi Link]] target exactly this, but it is untested.
> 3. **The biggest trust risks are false alarms with no recourse, scores tied to discipline, and
>    silent failure when Android kills the app.** Each has a cheap mitigation (below).

## 1. Dashcam companion apps

Garmin Drive, MyNextbase Connect, BlackVue, Viofo, 70mai, Thinkware Connected. Navigation
structure and clip-trimming UX could not be confirmed for any of them.

| App | Connection model | What stands out | Complaints found |
|---|---|---|---|
| Garmin Drive | Phone within ~3 m for setup, then auto-reconnect ([pairing](https://www8.garmin.com/manuals/webhelp/GUID-234ECA7B-7147-4142-80ED-C81970D02FF1/EN-GB/GUID-9983ED7E-888E-4AD6-A449-CBD17B7838C5.html)) | Incident detection texts emergency contacts with a location, **only after a contact is added and the feature is on**; needs an LTE subscription ([incident messaging](https://www8.garmin.com/manuals/webhelp/GUID-05C32B20-1E3D-4193-88A0-507B33C3434E/EN-US/GUID-4566CEE6-1817-4667-8D05-038D7D0E338B.html)) | Pairing stalls on the device-selection screen (App Store, anecdotal) |
| MyNextbase Connect | Bluetooth pairing, dual-band Wi-Fi | Red button saves the last 30 s to a protected folder. Emergency SOS needs the app in the background and cell service; free first year, then paid (press, unverified). iOS 4.0 from ~849 ratings | Slow or tricky Wi-Fi, pairing failures even after reinstalling ([permissions](https://support.nextbase.com/en/articles/612137-nextbase-app-permissions), [pairing help](https://support.nextbase.com/en/articles/618520-how-to-resolve-mynextbase-connect-pairing-problems)) |
| BlackVue | Camera Wi-Fi AP, no internet; Android silently falls back to cellular and loses the camera ([article](https://forum.blackvue.com/hc/en-us/articles/49128433566873-Solving-Problems-Caused-by-Automatic-Network-Switching)) | Free cloud tier with push notifications; pages disagree on its limits (unverified) | App slow or hanging, Wi-Fi drops, users remove and re-add the camera before every download; downloads fail when the app is backgrounded |
| Viofo | Join the camera Wi-Fi in phone settings first, then open the app ([guide](https://www.viofo.com/blogs/viofo-car-dash-camera-guide-faq-and-news/how-to-connect-the-viofo-app-and-what-to-do-if-the-connection-fails)) | n/a | The app does not notice the phone is on the camera Wi-Fi; drops and "device disconnected" errors; live view goes black |
| 70mai | Camera hotspot | n/a | Reconnect every time; needs Location on; account and login problems; privacy-policy concerns; about 3.3 stars (aggregator) |
| Thinkware Connected | Second app (Dash Cam Link) plus an LTE module for cloud features | Impacts above 3 g send an app notification and an emergency message to contacts; parked events ask consent before uploading a clip | About 2.2 stars from 85 Play reviews (weak signal); pricing pages conflict |

**Copy:** explicit prerequisites before SOS arms (Garmin) · protected pre/post-event capture · per-permission explanation
screens (Nextbase's help article reads like the screens Sahi should show) · auto-reconnect once paired · consent before a clip leaves the device (Thinkware).

**Avoid:** manual Wi-Fi join then return to the app · "Location: Always" without explaining why · forced accounts · two apps for one product · SOS that silently depends on the app staying alive · re-adding the device to recover a dropped link.

## 2. Driver-monitoring and fleet apps

Netradyne Driver•i, Samsara Driver, Lytx DriveCam, Motive Driver, Nauto, Seeing Machines
Guardian, Cipia Fleet Sense, Mobileye 8 Connect, and consumer phone-camera drowsiness apps.
Smart Eye returned nothing. One search per product, so depth is limited.

| Product | Driver-facing design | What the study found |
|---|---|---|
| Netradyne | DriverStars (good events), Streaks (stops, safe speed, distraction-free minutes), **Driver Dispute button** that notifies the safety manager ([STN](https://stnonline.com/industry-releases/netradyne-introduces-greenzone-score-enhancement-to-boost-driver-advocacy-and-safety)); in-cab voice plus app alerts | Drivers complain of false flags (a stop sign not facing his lane), stress from voice alerts, and resentment when the score drives a bonus ([Overdrive](https://www.overdriveonline.com/overdrive-extra/article/15742414/stop-netradyning-me-can-an-ai-coach-make-you-a-better-driver), summary only). Score formula not published. Sample consent form published |
| Samsara Driver | Scores, coaching tasks, trends, acknowledge events | Complaints are about crashes and lost data; no independent review of the score found |
| Lytx | Configurable retention; a no-video option that detects distraction patterns without recording the cab ([CCJ](https://www.ccjdigital.com/business/article/14940067/lytx-adds-risk-detection-alerts-without-recording-video)) | Acceptance rises when footage exonerates drivers (CTO statement; an 87% trade-press figure, unverified); Trustpilot reports violations flagged when none occurred |
| Motive Driver | Video review, risk scores | About 4.2–4.5 on Google Play (conflicting); complaints: mis-detections, battery drain, background behavior |
| Nauto | **Driver-first:** audible in-cab alert and self-coaching before the supervisor sees anything; alerts only while correction is still possible; three severity levels ([IEEE Spectrum](https://spectrum.ieee.org/ai-dashcam-driver-safety-nauto)) | The cleanest published alerting philosophy found |
| Seeing Machines Guardian | Fatigue flagged at ~1.5 s eye closure; audio plus seat vibration, then human review, then manager ([TT News](https://ttnews.com/articles/seeing-machines-unveils-guardian-system-monitor-driver-fatigue-distraction)) | Our <2–3 s closure target sits in the same range |
| Cipia Fleet Sense | On-device processing; separate driver warnings and filtered manager alerts; text-only or with video; **reports calibration loss, lens obstruction and tampering** ([SDC Exec](https://www.sdcexec.com/software-technology/press-release/21207160/cipia-cipia-releases-fleet-sense-driver-monitoring-device)) | Directly relevant to Sahi's calibration flow |
| Mobileye 8 Connect | Activation and configuration app only | No consumer reviews found |
| Consumer drowsiness apps (SleepSafe, Drowzy, etc.) | Phone camera eye-closure detection, sound and vibration, adjustable sensitivity | No independent false-alarm data; one academic paper reports ~86% on long blinks ([CarSafe](https://www.cs.dartmouth.edu/~campbell/carsafe.pdf)) |

**Copy:** alert the driver first, locally, escalating by severity (Nauto) · a **"this was wrong" button** that feeds tuning (Netradyne) · positive framing, not only penalties · show what triggers each alert and what is stored (Geotab's advice) · tamper and calibration-lost warnings (Cipia) · a metadata-only mode and retention limits (Lytx) · driver-adjustable sensitivity.

**Avoid:** tying scores to pay or discipline · opaque score formulas · repeated stressful voice alerts · false flags with no recourse · battery drain and lost data.

## 3. Crash detection and trip scoring

Google Pixel Car Crash Detection, Apple (reference only), Life360, Cambridge Mobile Telematics
DriveWell, Zendrive, Automatic, and Egypt context. Nothing found on Samsung SOS, Waze, Careem or Uber.

| Topic | Findings |
|---|---|
| Countdown UX | Pixel Watch: full-screen **60 s** countdown with "I'm OK"; the phone vibrates, rings loudly, asks aloud, and with no answer **auto-calls emergency on speakerphone** and shares location ([Google](https://support.google.com/googlepixelwatch/answer/12663810)). Pixel's detection does not run in airplane mode or Battery Saver |
| Detection method | Pixel uses sensors, location and ambient sound; no thresholds published. Life360: the car must reach about **25 mph within 5 s** before impact, though its own pages also say 30 s and quote battery floors of 10% and 20% ([support](https://support.life360.com/hc/en-us/articles/23053410919063-Life360-Free-Crash-Detection)). Not tested on motorcycles or scooters |
| False positives | iPhone 14 roller-coaster 911 calls ([MacRumors](https://www.macrumors.com/2022/10/09/iphone-14-crash-detection-on-rollercoaster/)). Life360 filters amusement parks and ski areas, still triggers on off-roading; an "I'm OK" stops escalation and a user can flag a false alarm ([support](https://support.life360.com/hc/en-us/articles/23053549450391-False-Collision-Alerts)) |
| Android battery killers | Xiaomi and Samsung rank among the worst ([DontKillMyApp](https://dontkillmyapp.com/problem)). Life360 tells users to set "Not optimized" and, on Samsung, "Never sleeping apps". Zendrive's SDK docs have per-vendor pages, including Xiaomi "No restrictions" ([docs](https://docs-sdk.zendrive.com/B7PG6rP8ujTHa19kFsBP/integrating-sdk/integrate/phone-restrictions)). A developer write-up says permissions can reset after OTA updates (single source, unverified) |
| Trip score | DriveWell inputs: speeding (seconds per drive hour), phone motion and screen interaction, hard braking and acceleration; **weights not published**; scale 40–100 per its page ([DriveWell](https://www.cmtelematics.com/drivewell-score/)). Automatic's score was criticised as too sensitive: ordinary stops triggered alerts (2013–2016 reviews) |
| Egypt | Calls to the ambulance number 123 are routed electronically by caller location. Roughly 1 in 10 calls is real (unverified), so fake calls are a known problem ([Egypt Today](https://www.egypttoday.com/Tag/137827/Fake-calls)). A 112 hotline was announced in 2022 ([Egyptian Streets](https://egyptianstreets.com/2022/11/01/112-egypt-announces-its-very-own-911-hotline-for-public-emergencies/)); whether it is live was not verified. No Egyptian crash-detection app was found |

**Copy:** long, loud countdown with vibration and a spoken prompt · speed gating (only arm above a driving speed) · "I'm OK" plus a "false alarm" flag that feeds tuning · a pre-flight checklist for "Always" location, battery exemption and autostart, re-checked on app update · DriveWell's definitions (speeding seconds per hour, phone interaction time).

**Avoid:** a single threshold with no context · conflicting numbers in docs (Life360) · over-sensitive hard-brake flags · failing silently in battery saver, offline or after the OEM killed the app · auto-dialing 123 without strong confirmation.

## 4. What to take: mapped to Sahi

Sahi's current state is from [[Phone-Pi Link]] and the app docs (`app/docs/` on `origin/app/crash-sos-trips`).

| # | Lesson | Sahi today | Proposed change | Evidence |
|---|---|---|---|---|
| 1 | Connection is the #1 complaint | In-app join, HTTP polling | Keep the in-app join and the BLE hybrid; spike on real phones | Dashcam complaints; [[Phone-Pi Link]] |
| 2 | Silent failure after an OEM battery kill | Crash detector arms only while the Pi is `online` | Phone-only crash arming; a visible **monitoring status** with a "monitoring paused" alert; a heartbeat | Nextbase SOS, DontKillMyApp, Life360 |
| 3 | Per-vendor battery guidance | Not seen in the app docs | Onboarding checklist: battery exemption, autostart, location "Always" with a reason per permission, re-check after updates | Nextbase, Life360, Zendrive |
| 4 | Countdown length | 30 s | Consider 45–60 s with a loud tone and spoken prompt from the start (judgment call: weigh the extra delay against false-alarm cost) | Pixel Watch 60 s |
| 5 | Speed gating and stillness | Detector is pure TypeScript on 100 Hz motion | Confirm it gates on prior speed and adds a post-impact stillness check; test roller-coaster-style spikes and dropped phones in the replay suite | Life360, iPhone 14 reports |
| 6 | Fake calls to 123 | Auto-dials 123 or the first contact after the countdown | Contacts first, strong confirmation before 123, **configurable emergency number** (123 / 112) | Egyptian fake-call reports |
| 7 | False alarms need recourse | None found | "This alert was wrong" button on alerts, incidents and the countdown; store it locally and use it to tune thresholds in Settings | Netradyne dispute, Life360 |
| 8 | Show what triggers alerts and what is stored | Privacy screen exists | Per-alert "why" text (reasons already come from `/alert`), plus what stays on the Pi/phone | Geotab advice, Lytx |
| 9 | Scores cause resentment | Trip score with weekly trend | Publish the formula, avoid framing it as a grade for others, add positive streaks, and keep the score driver-only | Netradyne reactions, DriveWell weights hidden |
| 10 | Tamper and calibration loss | Calibration is a guided step | Surface "calibration lost / camera covered" from the Pi to the phone as a warning | Cipia |
| 11 | Subscriptions gate SOS | SMS goes through the phone, no subscription | Keep it; this is a selling point | Garmin LTE, Nextbase paid SOS |
| 12 | Clip handling | Clip download in the incident screen | Protected pre/post capture (already planned), resumable downloads that survive backgrounding, and consent before sharing a clip off the phone | Thinkware, BlackVue |
| 13 | Driver-first alerting | Alerts from fusion's `AlertPattern` only | Keep driver-first and local; do not escalate to a third party without the driver's consent | Nauto, Seeing Machines |
| 14 | Arabic/RTL | Arabic and English built | No competitor evidence either way: a real differentiator. Verify RTL on the Live and SOS screens | Gap in all three groups |

## 5. Gaps nobody fills (Sahi's opening)

- **Driver-state alerts in a personal-vehicle, local-only product.** Fleet products are manager-centric with cloud review.
- **Watch heart-rate fusion**: none found.
- **Phone crash SOS tied to a driver-monitoring unit**: none found.
- **A transparent, driver-controlled score and sensitivity**: DriveWell and Zendrive do not publish weights.
- **Arabic/RTL driver UI**: no confirmed localized driver app.
- **Detecting that the OEM has killed the app**: not seen anywhere.
- **Motorcycles, microbuses and other vehicle types**: Life360 says it is untested on motorcycles. Relevant for Egypt; a test case for Sahi's detector.

## 6. Open items (not researched)

- Play Store listings and recent reviews for Life360, Zendrive-powered apps, and Egyptian apps (the ambulance authority's app name was not verified).
- Smart Eye, Waze, Samsung SOS, Careem and Uber driver-safety features.
- Gulf and Egyptian data-protection consent requirements for driver monitoring.
- A hands-on teardown: install two or three of these apps and walk through pairing, alerts and settings. The most valuable next step, and impossible from web research alone.
- Review mining at scale: a skill or script to pull Play Store reviews (the `app-store-reviews` skill I tried to install failed with an auth error).

## Sources

URLs are cited inline above. Search-only (not opened): Egypt Telegraph's list of what to tell the
dispatcher, Samsara's own 4.5 rating, and several price pages that contradict each other.
