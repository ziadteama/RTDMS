import type { IncidentRequest } from '@/pi/types';

export type QueuedIncident = IncidentRequest & { client_id: string; localId: number };
export type QueueEntry = { incident: QueuedIncident; status: 'pending' | 'failed'; attempts: number; nextAt: number };
export type QueueState = { entries: QueueEntry[]; sent: string[] };
export const emptyQueue = (): QueueState => ({ entries: [], sent: [] });
export const retryDelay = (attempt: number) => Math.min(60_000, 2_000 * 2 ** Math.min(attempt - 1, 5));

type Action = { type: 'enqueue'; incident: QueuedIncident; now: number } |
  { type: 'sent' | 'failed'; clientId: string; now: number };

/** Pure lifecycle: pending -> sent (removed, receipt retained) | failed -> retry. */
export function reduceQueue(state: QueueState, action: Action): QueueState {
  if (action.type === 'enqueue') {
    const id = action.incident.client_id;
    if (state.sent.includes(id) || state.entries.some((e) => e.incident.client_id === id)) return state;
    return { ...state, entries: [...state.entries, { incident: action.incident, status: 'pending', attempts: 0, nextAt: action.now }] };
  }
  if (!state.entries.some((e) => e.incident.client_id === action.clientId)) return state;
  if (action.type === 'sent') return {
    entries: state.entries.filter((e) => e.incident.client_id !== action.clientId),
    sent: [...state.sent, action.clientId],
  };
  return { ...state, entries: state.entries.map((e) => e.incident.client_id !== action.clientId ? e : {
    ...e, status: 'failed', attempts: e.attempts + 1, nextAt: action.now + retryDelay(e.attempts + 1),
  }) };
}

export type QueuePersistence = { load(): Promise<QueueState>; save(state: QueueState): Promise<void> };

/** Thin I/O shell. Serializes persistence and delivery; callers never await network delivery. */
export function createIncidentQueue(deps: {
  send(incident: QueuedIncident): Promise<boolean>; now(): number; persistence: QueuePersistence;
}) {
  let state = emptyQueue();
  let serial = deps.persistence.load().then((saved) => { state = saved; });
  const update = async (action: Action) => {
    state = reduceQueue(state, action);
    await deps.persistence.save(state);
  };
  const schedule = (work: () => Promise<void>) => {
    const result = serial.then(work);
    serial = result.catch(() => {});
    return result;
  };
  return {
    getState: () => state,
    enqueue: (incident: QueuedIncident) => schedule(() => update({ type: 'enqueue', incident, now: deps.now() })),
    flush: () => schedule(async () => {
      for (const entry of state.entries) {
        if (entry.nextAt > deps.now()) continue;
        const sent = await deps.send(entry.incident).catch(() => false);
        await update({ type: sent ? 'sent' : 'failed', clientId: entry.incident.client_id, now: deps.now() });
      }
    }),
  };
}
