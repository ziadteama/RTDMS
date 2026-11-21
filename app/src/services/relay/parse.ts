import type {
  ContactRegisterStatus,
  DeleteRegisterResponse,
  HealthResponse,
  RegisterResponse,
  RegisterResponseContact,
  SosGetResponse,
  SosPostResponse,
  SosResultContact,
  SosStatus,
} from './types';

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === 'string';

const REGISTER_STATUSES: readonly ContactRegisterStatus[] = ['pending', 'ok', 'opted_out', 'invalid', 'failed'];
const SOS_STATUSES: readonly SosStatus[] = ['queued', 'sent', 'delivered', 'read', 'failed', 'opted_out'];

export function parseRegisterResponse(v: unknown): RegisterResponse | null {
  if (!isObj(v) || !Array.isArray(v.contacts)) return null;
  const contacts: RegisterResponseContact[] = [];
  for (const item of v.contacts) {
    if (!isObj(item) || !isStr(item.phone_last4)) return null;
    if (!REGISTER_STATUSES.includes(item.status as ContactRegisterStatus)) return null;
    contacts.push({
      phone_last4: item.phone_last4,
      status: item.status as ContactRegisterStatus,
    });
  }
  return { contacts };
}

export function parseSosPostResponse(v: unknown): SosPostResponse | null {
  if (!isObj(v) || typeof v.ok !== 'boolean' || !isStr(v.client_id) || !Array.isArray(v.results)) return null;
  const results: { phone_last4: string; status: 'queued' }[] = [];
  for (const item of v.results) {
    if (!isObj(item) || !isStr(item.phone_last4) || item.status !== 'queued') return null;
    results.push({ phone_last4: item.phone_last4, status: 'queued' });
  }
  return { ok: v.ok, client_id: v.client_id, results };
}

export function parseSosGetResponse(v: unknown): SosGetResponse | null {
  if (!isObj(v) || !Array.isArray(v.results)) return null;
  const results: SosResultContact[] = [];
  for (const item of v.results) {
    if (!isObj(item) || !isStr(item.phone_last4)) return null;
    if (!SOS_STATUSES.includes(item.status as SosStatus)) return null;
    results.push({
      phone_last4: item.phone_last4,
      status: item.status as SosStatus,
    });
  }
  return { results };
}

export function parseDeleteResponse(v: unknown): DeleteRegisterResponse | null {
  if (!isObj(v) || typeof v.ok !== 'boolean') return null;
  return { ok: v.ok };
}

export function parseHealthResponse(v: unknown): HealthResponse | null {
  if (!isObj(v) || !isStr(v.whatsapp) || !isStr(v.version)) return null;
  if (!['connected', 'disconnected', 'pairing'].includes(v.whatsapp)) return null;
  return {
    whatsapp: v.whatsapp as 'connected' | 'disconnected' | 'pairing',
    version: v.version,
  };
}
