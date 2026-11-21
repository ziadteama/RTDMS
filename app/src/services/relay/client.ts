import { getInstallId } from '@/state/secure';
import { getRelayConfig, type RelayConfig } from './config';
import {
  parseDeleteResponse,
  parseHealthResponse,
  parseRegisterResponse,
  parseSosGetResponse,
  parseSosPostResponse,
} from './parse';
import type {
  DeleteRegisterResponse,
  HealthResponse,
  RegisterContact,
  RegisterResponse,
  SosGetResponse,
  SosPostResponse,
  SosRequestPayload,
} from './types';

export type RelayClientDeps = {
  fetch?: typeof fetch;
  getInstallId?: () => string;
  getConfig?: () => RelayConfig | null;
  timeoutSosMs?: number;
  timeoutDefaultMs?: number;
};

export type RelayClient = {
  register(driverName: string, contacts: RegisterContact[]): Promise<RegisterResponse | null>;
  sendSos(payload: SosRequestPayload): Promise<SosPostResponse | null>;
  sosStatus(clientId: string): Promise<SosGetResponse | null>;
  unregister(): Promise<DeleteRegisterResponse | null>;
  health(): Promise<HealthResponse | null>;
};

export function createRelayClient(deps: RelayClientDeps = {}): RelayClient {
  const fetchFn = deps.fetch ?? globalThis.fetch;
  const fetchInstallId = deps.getInstallId ?? getInstallId;
  const fetchConfig = deps.getConfig ?? getRelayConfig;
  const timeoutSosMs = deps.timeoutSosMs ?? 8_000;
  const timeoutDefaultMs = deps.timeoutDefaultMs ?? 10_000;

  async function request(path: string, options: { method: 'GET' | 'POST' | 'DELETE'; body?: unknown; timeoutMs: number; auth: boolean }) {
    const config = fetchConfig();
    if (!config && options.auth) return null;
    const url = `${config?.baseUrl ?? ''}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeoutMs);
    try {
      const headers: Record<string, string> = {};
      if (options.auth && config) {
        headers['Authorization'] = `Bearer ${config.apiKey}`;
        headers['X-Install-Id'] = fetchInstallId();
      }
      if (options.body !== undefined) {
        headers['Content-Type'] = 'application/json';
      }
      const res = await fetchFn(url, {
        method: options.method,
        headers,
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });
      if (!res.ok) return null;
      return await res.json().catch(() => null);
    } catch {
      return null;
    } finally {
      clearTimeout(timer);
    }
  }

  return {
    async register(driverName: string, contacts: RegisterContact[]): Promise<RegisterResponse | null> {
      const data = await request('/v1/register', {
        method: 'POST',
        body: { driver_name: driverName, contacts },
        timeoutMs: timeoutDefaultMs,
        auth: true,
      });
      return parseRegisterResponse(data);
    },

    async sendSos(payload: SosRequestPayload): Promise<SosPostResponse | null> {
      const data = await request('/v1/sos', {
        method: 'POST',
        body: payload,
        timeoutMs: timeoutSosMs,
        auth: true,
      });
      return parseSosPostResponse(data);
    },

    async sosStatus(clientId: string): Promise<SosGetResponse | null> {
      const data = await request(`/v1/sos/${encodeURIComponent(clientId)}`, {
        method: 'GET',
        timeoutMs: timeoutDefaultMs,
        auth: true,
      });
      return parseSosGetResponse(data);
    },

    async unregister(): Promise<DeleteRegisterResponse | null> {
      const data = await request('/v1/register', {
        method: 'DELETE',
        timeoutMs: timeoutDefaultMs,
        auth: true,
      });
      return parseDeleteResponse(data);
    },

    async health(): Promise<HealthResponse | null> {
      const config = fetchConfig();
      if (!config) return null;
      const data = await request('/v1/health', {
        method: 'GET',
        timeoutMs: timeoutDefaultMs,
        auth: false,
      });
      return parseHealthResponse(data);
    },
  };
}

export const relay = createRelayClient();
