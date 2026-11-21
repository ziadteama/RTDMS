import type { RelayClient } from './client';
import type {
  DeleteRegisterResponse,
  HealthResponse,
  RegisterContact,
  RegisterResponse,
  SosGetResponse,
  SosPostResponse,
  SosRequestPayload,
  SosStatus,
} from './types';

/**
 * In-process fake relay client for demo mode.
 * Does not hit the network; provides simulated progression for SOS receipts.
 */
export function createFakeRelayClient(deps: { now?: () => number } = {}): RelayClient {
  const clock = deps.now ?? Date.now;
  let contactsList: RegisterContact[] = [];
  const incidents = new Map<string, { createdAt: number; last4s: string[] }>();

  return {
    async register(_driverName: string, contacts: RegisterContact[]): Promise<RegisterResponse> {
      contactsList = [...contacts];
      return {
        contacts: contacts.map((c) => ({
          phone_last4: c.phone.slice(-4),
          status: 'ok',
        })),
      };
    },

    async sendSos(payload: SosRequestPayload): Promise<SosPostResponse> {
      const last4s = contactsList.map((c) => c.phone.slice(-4));
      incidents.set(payload.client_id, {
        createdAt: clock(),
        last4s,
      });
      return {
        ok: true,
        client_id: payload.client_id,
        results: last4s.map((phone_last4) => ({ phone_last4, status: 'queued' })),
      };
    },

    async sosStatus(clientId: string): Promise<SosGetResponse> {
      const incident = incidents.get(clientId);
      if (!incident) {
        return { results: [] };
      }
      const elapsed = clock() - incident.createdAt;
      let status: SosStatus = 'queued';
      if (elapsed >= 10_000) {
        status = 'delivered';
      } else if (elapsed >= 5_000) {
        status = 'sent';
      }
      return {
        results: incident.last4s.map((phone_last4) => ({ phone_last4, status })),
      };
    },

    async unregister(): Promise<DeleteRegisterResponse> {
      contactsList = [];
      incidents.clear();
      return { ok: true };
    },

    async health(): Promise<HealthResponse> {
      return { whatsapp: 'connected', version: '1' };
    },
  };
}

export const fakeRelayClient = createFakeRelayClient();
