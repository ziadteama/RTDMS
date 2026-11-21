import type { Contact } from '@/state/secure';
import { useSettings } from '@/state/settings';
import { normalizeE164 } from '../phone';
import { relay, type RelayClient } from './client';

/**
 * Synchronizes the emergency contacts list with the WhatsApp relay server.
 * Pure logic around the relay client; if the relay is unreachable, contacts
 * are marked with status 'failed' but remain fully saved for SMS.
 */
export async function syncRelayContacts(
  driverName: string,
  contacts: Contact[],
  relayClient?: RelayClient,
): Promise<Contact[]> {
  // Demo mode never fabricates a registration result: contacts stay as saved.
  if (!relayClient && useSettings.getState().demo) return contacts;
  const client = relayClient ?? relay;

  if (contacts.length === 0) {
    try {
      await client.unregister();
    } catch {
      // best-effort
    }
    return [];
  }

  const registerPayload = contacts.map((c) => ({
    name: c.name,
    phone: normalizeE164(c.phone),
  }));

  try {
    const res = await client.register(driverName, registerPayload);
    if (res?.contacts) {
      return contacts.map((c) => {
        const last4 = normalizeE164(c.phone).slice(-4);
        const match = res.contacts.find((rc) => rc.phone_last4 === last4);
        return {
          ...c,
          phone: normalizeE164(c.phone),
          relayStatus: match?.status ?? 'pending',
        };
      });
    }
  } catch {
    // fall through to failed status
  }

  // If unreachable, keep saved and mark failed
  return contacts.map((c) => ({
    ...c,
    phone: normalizeE164(c.phone),
    relayStatus: 'failed',
  }));
}
