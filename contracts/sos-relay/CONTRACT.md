# SOS relay contract (version 1): phone app -> relay server -> WhatsApp

Owner: the coordinator (changes via the board's CR process, like `contracts/pi-link/`).
Decision (user, 2026-11-21): the crash SOS is sent **WhatsApp first, SMS as backup**, through a small
server we run that uses an **unofficial WhatsApp library (Baileys)** from a dedicated team WhatsApp
account. The ban risk was accepted by the user. SMS (link-free, see the app's SOS template) is
always sent as well, because the relay needs mobile data and SMS does not.

All requests: HTTPS, JSON, `Authorization: Bearer <RELAY_API_KEY>`, header `X-Install-Id: <uuid>`
(random per app install, created on first run). Phone numbers are E.164 (`+201001234567`).

## Endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/v1/register` | `{"driver_name": "Ziad", "contacts": [{"name": "Mum", "phone": "+20..."}]}` (max 5, replaces the install's list) | `{"contacts": [{"phone_last4": "4567", "status": "pending"|"ok"|"opted_out"|"invalid"|"failed"}]}` |
| POST | `/v1/sos` | `{"client_id": "<uuid>", "kind": "crash"|"manual", "t_crash": 1795189202400, "lat": 30.04440, "lon": 31.23570}` (lat/lon may be null) | `{"ok": true, "client_id": "...", "results": [{"phone_last4": "4567", "status": "queued"}]}` |
| GET | `/v1/sos/{client_id}` | | `{"results": [{"phone_last4": "4567", "status": "queued"|"sent"|"delivered"|"read"|"failed"|"opted_out"}]}` |
| DELETE | `/v1/register` | | `{"ok": true}` (removes the install and its contacts) |
| GET | `/v1/health` | | `{"whatsapp": "connected"|"disconnected"|"pairing", "version": "1"}` (no auth needed) |

Rules:
- `/v1/sos` sends **only to contacts registered for that install**; any other number is impossible
  (no open relay). Idempotent on `client_id` (a retry returns the same result, never a second message).
- Limits: 5 contacts per install, 5 SOS per install per hour, 60 requests per minute per key. Excess
  returns `429`.
- On `/v1/register` the relay sends each **new** contact one opt-in message: "<driver> added you as an
  emergency contact in Sahi. You will get a message if their car's crash alert fires. Reply STOP to
  opt out." A contact that replies `STOP` becomes `opted_out` and never receives SOS messages.
- SOS message text (WhatsApp may carry a link): `SAHI crash alert {hh:mm AM/PM}. {driver_name} may
  need help. Location: {lat},{lon} https://maps.google.com/?q={lat},{lon}` (or `Location unknown` when
  lat/lon are null; `kind: manual` says "needs help" with no "crash").
- Statuses come from WhatsApp receipts (sent / delivered / read) via `GET /v1/sos/{client_id}`; the
  app shows the real status and never says "delivered" otherwise.

## Privacy and security (binding)

- Stored: only the install id, driver name, registered contact numbers and opt-out flags. **Never**
  stored beyond 24 h: SOS payloads and coordinates (in memory or a TTL store). Logs mask numbers
  (last 4 digits only) and never contain coordinates.
- The API key lives in the server env and in the app's build config, never in git.
  An APK-embedded key is extractable: acceptable for the prototype, limited by the per-install
  allowlist, the opt-in message and the rate limits.
- The app tells the driver, in plain words, that emergency contacts get a WhatsApp message through
  the Sahi service and that their location is sent only when an alert fires (consent screen).

## Not in v1

Two-way chat, group messages, media, multiple drivers per account, delivery to non-WhatsApp numbers
(SMS covers those).
