import type { IncomingMessage, ServerResponse } from 'node:http';

type RelayContact = { name: string; phone: string };
type RelayInstall = { driver_name: string; contacts: RelayContact[] };
type RelaySosIncident = { createdAt: number; contacts: RelayContact[] };

const installs = new Map<string, RelayInstall>();
const incidents = new Map<string, RelaySosIncident>();

function json(res: ServerResponse, body: unknown, code = 200) {
  const b = Buffer.from(JSON.stringify(body));
  res.writeHead(code, {
    'Content-Type': 'application/json',
    'Content-Length': b.length,
    'Cache-Control': 'no-store',
  });
  res.end(b);
}

async function parseBody(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  const s = Buffer.concat(chunks).toString('utf8');
  return s ? JSON.parse(s) : {};
}

/**
 * Mock WhatsApp SOS relay stub adhering to CONTRACT.md.
 * Provides scripted status progression: queued -> sent -> delivered.
 */
export async function handleRelayRequest(
  req: IncomingMessage,
  res: ServerResponse,
  path: string,
): Promise<boolean> {
  if (!path.startsWith('/v1/')) return false;

  if (req.method === 'GET' && path === '/v1/health') {
    json(res, { whatsapp: 'connected', version: '1' });
    return true;
  }

  const authHeader = req.headers['authorization'];
  const installId = req.headers['x-install-id'] as string | undefined;

  if (!authHeader?.startsWith('Bearer ') || !installId) {
    json(res, { error: 'Unauthorized: Bearer token and X-Install-Id required' }, 401);
    return true;
  }

  if (req.method === 'POST' && path === '/v1/register') {
    const b = (await parseBody(req)) as { driver_name?: string; contacts?: RelayContact[] };
    const driver_name = b.driver_name ?? 'Driver';
    const contacts = Array.isArray(b.contacts) ? b.contacts.slice(0, 5) : [];
    installs.set(installId, { driver_name, contacts });
    json(res, {
      contacts: contacts.map((c) => ({
        phone_last4: c.phone.replace(/\D/g, '').slice(-4),
        status: 'pending',
      })),
    });
    return true;
  }

  if (req.method === 'POST' && path === '/v1/sos') {
    const b = (await parseBody(req)) as { client_id?: string; kind?: string; t_crash?: number };
    if (!b.client_id) {
      json(res, { error: 'client_id is required' }, 400);
      return true;
    }
    const install = installs.get(installId);
    const contacts = install?.contacts ?? [];
    if (!incidents.has(b.client_id)) {
      incidents.set(b.client_id, { createdAt: Date.now(), contacts });
    }
    json(res, {
      ok: true,
      client_id: b.client_id,
      results: contacts.map((c) => ({
        phone_last4: c.phone.replace(/\D/g, '').slice(-4),
        status: 'queued',
      })),
    });
    return true;
  }

  const sosMatch = path.match(/^\/v1\/sos\/([^/]+)$/);
  if (req.method === 'GET' && sosMatch) {
    const clientId = decodeURIComponent(sosMatch[1]!);
    const incident = incidents.get(clientId);
    if (!incident) {
      json(res, { results: [] });
      return true;
    }
    const elapsed = Date.now() - incident.createdAt;
    const status = elapsed < 5_000 ? 'queued' : elapsed < 10_000 ? 'sent' : 'delivered';
    json(res, {
      results: incident.contacts.map((c) => ({
        phone_last4: c.phone.replace(/\D/g, '').slice(-4),
        status,
      })),
    });
    return true;
  }

  if (req.method === 'DELETE' && path === '/v1/register') {
    installs.delete(installId);
    json(res, { ok: true });
    return true;
  }

  return false;
}
