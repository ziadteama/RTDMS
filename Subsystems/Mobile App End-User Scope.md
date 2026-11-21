---
title: "Mobile App End-User Scope — Sahi is a product for the driver"
tags:
  - subsystem
  - app
  - mobile
  - product
  - decisions
aliases:
  - Sahi end-user scope
  - Sahi audience
status: decided
decided: 2026-11-21
---

# Mobile App End-User Scope

↑ [[Home]] | App note: [[Mobile App]] | Link design: [[Phone-Pi Link]] | Lessons from other apps: [[Competitor App Study]]

> [!abstract] Decision (2026-11-21, user)
> **Sahi is a consumer-grade product for the driver, not an admin or engineering tool.** Anything
> that only the team needs (hardware health, thresholds, model switches, restart/shutdown, raw
> metrics) leaves the main app. The always-on rule is `.cursor/rules/end-user-product.mdc`.
> Fleet managers and OEMs would need a separate dashboard; that is out of scope here.

## Who the user is and what they need

Desk research only (the [[Competitor App Study]], Egypt crash and emergency-call findings, and the
report's objectives). **Not yet validated with drivers**: see [[#Validate with real drivers]].

| The driver needs to… | So the app must… | Not… |
|---|---|---|
| Know at a glance they are fine to drive | show one big state (Alert / Drowsy / Distracted / Phone) in the alert colors, and stay quiet when all is well | show metrics they must interpret |
| Be woken or warned in time | rely on the unit's buzzer as the primary alert; the phone adds voice and haptics | depend on the phone to be looked at |
| Get help after a crash without doing anything | detect on the phone alone, warn loudly, message contacts, and only call 123 if they stay unresponsive | wait on the unit being connected |
| Trust it | say plainly what is stored (on the phone only), let them delete everything, never share a score | frame the score as a grade for someone else |
| Not be annoyed | alert rarely and correctly; one tap to say "this alert was wrong" | expose threshold sliders to tune it |
| Set up once and forget | a short guided setup: connect the unit, set the driving position, add contacts | make them manage services or settings later |
| See how they are doing | simple trip history and a transparent score with its reasons | raw sensor numbers |

## Audit: what is admin or engineer-facing today

Found by sweeping `app/src` and `app/docs` on `main` (2026-11-21) and the Stitch screens.

| Where | What | Verdict |
|---|---|---|
| `tab.health` "Pi" tab (`app/src/screens/health.tsx`) | CPU %, throttle bits, 5 V rail, memory, disk, per-model status, **Restart and Shut down the Pi** | **Move to hidden Diagnostics.** The driver gets one plain "Your Sahi unit" status |
| Settings → "Detection (on the Pi)" | thresholds in seconds (eye closure, gaze, phone), per-detector on/off, profile | **Replace** with a Low / Normal / High sensitivity choice; thresholds and detector switches go to Diagnostics |
| Settings → Connection | typed "Pi address" | **Move** to pairing's "Having trouble?" and Diagnostics |
| Live tab | EAR/PERCLOS/blink numbers, HR/RR groups, MJPEG camera view | **Simplify:** state + status pill; camera preview only inside setup and calibration (a live video feed is a distraction while driving) |
| Copy | "Pi", "fusion", "MJPEG", "fps", "FOV 110° · IR 940nm", "monitoring paused" jargon | **Rewrite** in plain words ("your Sahi unit", "camera") |
| `app/docs/ux/flow-2-status.md` | tapping the status pill opens a "System Diagnostics" dialog | **Replace** with a plain explanation of the state; diagnostics only via the hidden entry |
| Demo mode, replay data | useful for the team and the final presentation | **Keep but hide** behind Diagnostics |
| Pairing token and `rtdms-admin rotate-token` (CONTRACT, hard-cases) | a CLI on the Pi is fine for the team; a driver has no way to run it | **Open product question** below |

## Target app structure

Three tabs (the earlier four-tab idea dropped "Alerts": alert history already lives in each trip).

| Tab | Content |
|---|---|
| **Drive** | big driver state, a small status pill ("Monitoring · unit connected"), one line of context ("45 km/h · 32 min"). Driving lock hides everything else |
| **Trips** | trip list, score with the reasons, timeline, saved incident clips |
| **Settings** | Your Sahi unit (status, "Set up driving position", "Forget this unit"), Alerts (sound, voice volume, vibration, sensitivity Low/Normal/High, test alert), Emergency (contacts, countdown length, who to call), Privacy and my data, About |

Hidden **Diagnostics** (tap the version number 7 times): the former Pi tab, thresholds, detector
switches, address entry, demo mode, restart/shutdown, raw metrics. Labeled "for the Sahi team".

## Rules that follow

1. **Audience test:** every screen, setting and string must pass "would a driver who has never
   seen the code know what this is and why they would touch it?" If not, it goes to Diagnostics or
   is removed.
2. **Vocabulary:** driver-facing words only (see the rule file's table).
3. **Defaults over settings:** the driver should rarely need to change anything. Prefer a good
   default, then a 3-way choice, then Diagnostics; never a numeric threshold.
4. **No metrics without meaning:** show a state or a plain sentence, not a raw number, unless the
   driver can act on it.
5. **The team's tools are not dead code:** they stay, hidden, because the team and the supervisor
   need them for tuning and demos.

## Open product questions

1. **How does a driver get the pairing QR?** The Pi has no screen. The contract says the Pi
   generates a token on first start and shows a QR on its setup page, which is an installer
   workflow, not a product one. Likely answer: provision the token at manufacturing and print the
   QR on the unit's label and box; "Forget this unit" and re-pair stay in the app. **Needs a
   decision from the team.**
2. **Who sets up the unit in the car?** Camera mounting and the driving position are physical
   steps: does the driver do it from a guided in-app flow, or an installer?
3. **One driver or several?** The app has calibration profiles. For a personal car, one profile is
   enough; shared cars would need profile switching. Default to one.
4. **Fleet and OEM use** needs a manager view and a different consent model; deliberately out of
   this scope.

## Validate with real drivers

The project's data collection plan already involves 10–20 volunteer drivers
([[Mobile App]] and the report's Phase Two plan). Before the UI PR is built, run a 15-minute
test with **at least 5** of them on the wireframes (the Stitch screens or paper): can they tell
what state they are in, pair the unit, add a contact, find "this alert was wrong", and explain what
Sahi stores? Record results here. Until then this note is a hypothesis built from desk research.

## What changes in the docs and plan

- `app/docs/DESIGN.md`, `UX.md`, `ux/*` and `lifecycle/*`: restructure to the table above (the app
  orchestrator does this; see the board entry of 2026-11-21).
- [[Mobile App]]: audience line and the MVP table rows 1 and 7 updated (done with this note).
- Stitch screens: redraw the Pi tab as "Device status" inside Settings and drop the numeric
  overlays and the GitHub glyph.
- App code: `tab.health` becomes Diagnostics; `settings` split into Alerts / Emergency / Unit
  sections; i18n copy rewritten.
