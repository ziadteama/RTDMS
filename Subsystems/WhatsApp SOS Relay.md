---
title: "WhatsApp SOS Relay"
tags:
  - subsystem
  - relay
  - sos
  - whatsapp
aliases:
  - SOS Relay
  - relay server
status: verified-end-to-end-via-script-app-test-pending
updated: 2026-11-21
---

# WhatsApp SOS Relay

Small server in `relay/` that turns a crash alert from the Sahi phone app into a WhatsApp message to the driver's emergency contacts. Spec: `contracts/sos-relay/CONTRACT.md` (v1). Code: `relay/` (README there has the run instructions). Related: [[Mobile App]], [[Phone-Pi Link]], [[Pi Runtime]].

> [!success] Update 2026-11-22
> Linked a dedicated number and **verified end to end** with the smoke script: register → opt-in → test SOS
> → `delivered`; the recipient confirmed the messages arrived. Runs on the dev machine on port 8088; the
> phone reaches it over Tailscale. The first real-mode start crashed (Node strip-only mode) and was
> fixed in PRs #39/#40. **Not yet verified:** the app → relay path with demo mode off, inbound `STOP`, and
> reconnect after a dropped session. See [[Project Log 2026-11]] and [[Dev Environment and Test Devices]].

> [!warning] Status
> Built and tested against a fake transport and a dry-run instance. **Never run against real WhatsApp**: no account linked, no message sent, receipts and inbound `STOP` unverified.

## Purpose

SMS is the always-on backup, but it needs no data and the carrier filters some content (links were dropped in our test). WhatsApp gives a link, real delivery and read receipts, and works over data. The phone needs mobile data at crash time for this path; SMS does not.

## Decision record

- 2026-11-21, user: send **WhatsApp first, SMS as backup**; both are sent, SMS always.
- WhatsApp's official Business API needs a verified business and templates; we use the **unofficial Baileys library** (`@whiskeysockets/baileys`, pinned 6.7.24) from a dedicated team number.
- **Ban / ToS risk accepted by the user.** The account can be banned or logged out at any time.
- Team-run server rather than a third-party SMS/WhatsApp vendor: no cost, no vendor holding contacts.

## Architecture

```
app --HTTPS--> http router --> services (register / sos / inbound)
                                  |-> SQLite: installs, contacts, opt_outs
                                  |-> in-memory SOS store (24 h TTL)
                                  `-> WhatsAppTransport (interface)
                                        |- BaileysTransport (real)
                                        |- DryRunTransport (--dry-run, masked logs)
                                        `- FakeTransport (tests)
```

Pure core (message text, validation, limiter, status ranks) with the clock, DB and transport injected. Session files live in a mounted `auth/` dir; pairing is by QR printed in the terminal, and `GET /v1/health` shows `pairing`.

## API summary

`POST/DELETE /v1/register`, `POST /v1/sos`, `GET /v1/sos/{client_id}`, `GET /v1/health`. Bearer `RELAY_API_KEY` plus `X-Install-Id` (uuid). Limits: 5 contacts, 5 SOS per install per hour, 60 requests per minute per key (429). SOS is idempotent on `client_id` and can only address contacts registered for that install. Full shapes in the contract.

## Privacy and retention

- Stored: install id, driver name, contact numbers, opt-out flags (SQLite).
- Never stored beyond 24 h, memory only: SOS payloads, coordinates, per-contact statuses.
- Logs mask numbers to the last 4 digits and never contain coordinates or message bodies.
- New contacts get one opt-in message; `STOP` replies are recorded as opt-outs and honored for every install, even after the install was deleted.
- The app must show a plain-words consent screen (contract).

## Ops

- Link the number: run the server, watch for the QR / `pairing`, scan with WhatsApp > Linked devices on the dedicated SIM. Keep the auth dir.
- **Always on (22 Nov):** systemd user service `rtdms-relay` (`relay/deploy/rtdms-relay.service`, installed with `relay/deploy/install-service.sh`). `Restart=always`, secrets from `~/RTDMS-coord/relay-data/relay.env` (outside git), the WhatsApp session in `relay-data/auth`. Tested: `kill -9` brought it back in 5 s. It starts at boot only after `sudo loginctl enable-linger <user>`; sleep and suspend are masked on the dev machine. It runs from the checkout in `~/RTDMS/relay`, so a branch switch there changes the code at the next restart.
- **Re-link after a logout (401):** `relay/deploy/relink-whatsapp.sh start` renames the old `auth/` (kept as `auth.logged-out-<time>`, never deleted), restarts the service and keeps the newest pairing QR in `relay-data/qr.txt`; `show` draws it in the terminal. Scan on the relay's phone: WhatsApp → Linked devices → Link a device. If the terminal output does not reach you, render `qr.txt` to a PNG and open that. Delete `qr.txt`/PNG afterwards (they hold pairing material). **Done on 22 Nov 17:05:** linked, then restart and `kill -9` both reconnected with no QR. Logged out on the first start under the service; cause unknown. Check with `curl localhost:8088/v1/health` (`whatsapp` should be `connected`) and `journalctl --user -u rtdms-relay`.
- HTTPS is not set up by the repo. Options: Cloudflare Tunnel, Tailscale Funnel, or a VPS with Caddy. See `relay/README.md`.
- Docker: `relay/Dockerfile` and `compose.yaml` (volumes for `auth/` and `data/`). Not built yet.

## Risks

- Unofficial library: ban, forced logout or protocol break after a WhatsApp update.
- Session expiry needs a human to re-scan the QR.
- Needs mobile data on the phone at crash time.
- Inbound `STOP` from `@lid` addresses is skipped (limitation); to verify live.
- Unknown-sender spam: any sender's `STOP` is stored as a number only; no other inbound text is kept.
- The API key embedded in the APK is extractable; limited by the per-install allowlist, opt-in and rate limits.

## Status

Built, 70 tests pass, dry-run smoke passes. Not verified: real send, delivery/read receipts, inbound `STOP`, Docker build, HTTPS exposure.
