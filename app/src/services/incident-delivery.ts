import type { PiTransport } from '@/pi/transport';
import { db } from '@/state/db';
import { queuePersistence } from '@/state/incident-queue';
import { kv } from '@/state/storage';
import { createIncidentQueue, type QueuedIncident } from './incident-queue';
import { pi } from './pi';

export function incidentSender(transport: () => PiTransport) {
  return async ({ localId, ...body }: QueuedIncident): Promise<boolean> => {
    const result = await transport().send('POST', '/incident', body);
    const id = (result as { id?: unknown } | null)?.id;
    if (typeof id !== 'string') return false;
    db.saveIncident(localId, { piId: id });
    return true;
  };
}

export const incidentQueue = createIncidentQueue({
  send: incidentSender(pi), now: Date.now, persistence: queuePersistence(kv),
});

export function startIncidentDelivery(): () => void {
  const flush = () => { void incidentQueue.flush().catch(() => {}); };
  flush();
  const timer = setInterval(flush, 1000);
  return () => clearInterval(timer);
}

/** UUID v4 correlation key, not a credential; injected RNG makes the format testable. */
export function incidentClientId(random = Math.random): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const value = Math.floor(random() * 16);
    return (c === 'x' ? value : (value & 3) | 8).toString(16);
  });
}
