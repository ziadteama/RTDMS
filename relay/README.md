# Sahi SOS Relay Server

A dedicated microservice for relaying crash alerts from the Sahi mobile app to emergency contacts over WhatsApp (via Baileys) with SMS as an independent fallback.

Full specification and protocol rules are documented in [CONTRACT.md](file:///home/teamacs/RTDMS/.claude/worktrees/agent-a889c65bcc8ea92ae/contracts/sos-relay/CONTRACT.md).

---

## 1. Quick Start & Local Development

### Prerequisites
- Node.js 22.13+
- npm

### Installation & Test
```bash
cd relay
npm ci
npm test              # Run unit tests via vitest
npm run typecheck     # Validate TypeScript types
npm run lint          # Run ESLint checks
```

### Running Locally in Dry-Run Mode
Dry-run mode starts the service without attempting real WhatsApp connections or sending messages over the network:
```bash
cp .env.example .env
# Edit .env and ensure:
# RELAY_DRY_RUN=true
npm start
```

---

## 2. Running in Docker

A production-ready multi-stage Dockerfile and Docker Compose configuration are provided:

```bash
cd relay
cp .env.example .env
# Set RELAY_API_KEY to a secure random string in .env
docker compose up -d --build
docker compose logs -f relay
```

The container runs as non-root user `node`, exposes port `8787` on `127.0.0.1`, and persists data and credentials to `./auth` and `./data`.

---

## 3. How to Link the Dedicated WhatsApp Number

> [!IMPORTANT]
> **Use a dedicated SIM / phone number** exclusively for this relay service. Never link a personal WhatsApp account.

1. Start the relay server (`npm start` or `docker compose up`).
2. Query health: `curl http://127.0.0.1:8787/v1/health` returns `{"whatsapp": "pairing", "version": "1"}`.
3. Check the relay terminal logs. A raw QR string is printed when emitted:
   - To render as an ASCII QR code in your terminal, run:
     ```bash
     qrencode -t ANSIUTF8 "<raw-qr-string>"
     ```
   - Alternatively, view the QR code in any standard QR generator or terminal tool.
4. On the dedicated WhatsApp phone:
   - Open WhatsApp -> **Settings** (or three dots) -> **Linked devices** -> **Link a device**.
   - Scan the terminal QR code within ~60 seconds before it rotates.
5. Once scanned, `GET /v1/health` switches to `{"whatsapp": "connected", "version": "1"}`.
6. The session credentials persist inside the mounted auth directory (`./auth` or `/app/auth`). **Do not delete the auth directory** unless you intentionally want to unlink and re-pair the number.

---

## 4. How to Expose Over HTTPS

The relay binds to `127.0.0.1:8787`. HTTPS termination must be handled by an external reverse proxy or tunnel. **Nothing is set up by this repo.** Recommended options:

- **Cloudflare Tunnel (Cloudflared)**: Run `cloudflared tunnel run <tunnel-name>` pointing to `http://127.0.0.1:8787`. Provides DDoS protection, global CDN routing, and free automatic HTTPS without opening inbound firewall ports.
- **Tailscale Funnel**: Run `tailscale funnel 8787` to route a public Tailscale node DNS name with automatic TLS certificates directly to your relay service on localhost.
- **VPS with Caddy**: Deploy the container on a VPS with ports 80/443 open. Add a Caddyfile directive `relay.example.com { reverse_proxy 127.0.0.1:8787 }`. Caddy provisions and renews Let's Encrypt TLS certificates automatically.

---

## 5. Unofficial Library Ban & ToS Risk

> [!WARNING]
> This service connects via `@whiskeysockets/baileys` (an unofficial WhatsApp Web reverse-engineered client).

- **User Acceptance**: WhatsApp terms of service strictly prohibit automated and unofficial clients. WhatsApp may ban, flag, or log out the relay account at any moment without notice. This operational risk was explicitly accepted by the user.
- **SMS Backup**: The mobile app **always** sends an independent direct SMS to emergency contacts when a crash alert fires. SMS requires no mobile data and guarantees alert delivery even if the WhatsApp account is disconnected or banned.

---

## 6. Privacy & Security Rules

All privacy constraints defined in [CONTRACT.md](file:///home/teamacs/RTDMS/.claude/worktrees/agent-a889c65bcc8ea92ae/contracts/sos-relay/CONTRACT.md) are strictly enforced:

- **Stored Data**: SQLite stores only install IDs, driver names, registered contact numbers, and opt-out flags.
- **TTL Limit**: SOS payloads, GPS coordinates, and alert history are **never stored beyond 24 hours** (in-memory or TTL store).
- **Masked Logs**: Phone numbers are masked in all logs (last 4 digits only, e.g. `***4567`). Message bodies and GPS coordinates are **never logged**.
- **Opt-in & STOP**: Upon contact registration (`POST /v1/register`), each new contact receives an opt-in message explaining the service. Replying `STOP` immediately marks the contact as `opted_out`.
- **No Open Relay**: The relay only delivers SOS messages to contacts previously registered for that specific install ID. Arbitrary recipient routing is rejected.

---

## 7. API Summary

Refer to [CONTRACT.md](file:///home/teamacs/RTDMS/.claude/worktrees/agent-a889c65bcc8ea92ae/contracts/sos-relay/CONTRACT.md) for full request/response schemas.

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `GET` | `/v1/health` | No | Returns WhatsApp transport state (`connected`, `disconnected`, `pairing`) |
| `POST` | `/v1/register` | Yes | Registers driver and emergency contacts (max 5); sends opt-in message |
| `DELETE` | `/v1/register` | Yes | Removes the app install ID and its registered contacts |
| `POST` | `/v1/sos` | Yes | Queues SOS alert for registered contacts; idempotent on `client_id` |
| `GET` | `/v1/sos/{client_id}` | Yes | Retrieves delivery statuses (`queued`, `sent`, `delivered`, `read`, `failed`) |

Requests require header `X-Install-Id: <uuid>` and `Authorization: Bearer <RELAY_API_KEY>`.

---

## 8. Environment Variables

| Variable | Default | Description |
|---|---|---|
| `RELAY_API_KEY` | *(required)* | Bearer authentication key for API access. |
| `PORT` | `8787` | Port the HTTP server listens on. |
| `RELAY_DB_PATH` | `./data/relay.db` | Filepath to SQLite database. |
| `RELAY_AUTH_DIR` | `./auth` | Filepath to Baileys multi-file authentication session storage. |
| `RELAY_TZ` | `Africa/Cairo` | Local timezone for alert timestamp formatting. |
| `RELAY_DRY_RUN` | `false` | When `true`, uses DryRunTransport (no real WhatsApp connection). |

---

## 9. Known Limitations

1. **Inbound WhatsApp Privacy LIDs**: Contacts whose WhatsApp clients send messages using internal Linked Identity Devices (`@lid`) rather than standard phone JIDs (`@s.whatsapp.net`) cannot have their E.164 phone numbers resolved. Inbound messages from `@lid` are skipped with a masked debug log.
2. **Receipts Require Recipient Data**: Delivery (`delivered`) and read (`read`) receipts require the recipient's mobile phone to be connected to the internet.
3. **Session Expiry & Logouts**: WhatsApp Web sessions can expire after prolonged network disconnects or if logged out via the WhatsApp mobile application. If logged out (`401`), the auth directory must be emptied and the number re-paired.
