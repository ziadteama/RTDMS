import type { StateStorage } from 'zustand/middleware';

import { queuePersistence } from '@/state/incident-queue';

import {
  createIncidentQueue,
  emptyQueue,
  reduceQueue,
  retryDelay,
  type QueuedIncident,
  type QueuePersistence,
  type QueueState,
} from './incident-queue';

function memoryStorage(): StateStorage {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, val: string) => {
      map.set(key, val);
    },
    removeItem: (key: string) => {
      map.delete(key);
    },
  };
}

describe('incident-queue', () => {
  const dummyIncident: QueuedIncident = {
    client_id: 'test-uuid-1',
    localId: 42,
    t_crash: 1_700_000_000_000,
    g_peak: 6.2,
    lat: 30.05,
    lon: 31.25,
  };

  describe('retryDelay', () => {
    it('applies exponential backoff starting at 2 s and capped at 60 s', () => {
      expect(retryDelay(1)).toBe(2_000);
      expect(retryDelay(2)).toBe(4_000);
      expect(retryDelay(3)).toBe(8_000);
      expect(retryDelay(4)).toBe(16_000);
      expect(retryDelay(5)).toBe(32_000);
      expect(retryDelay(6)).toBe(60_000);
      expect(retryDelay(7)).toBe(60_000);
      expect(retryDelay(100)).toBe(60_000);
    });
  });

  describe('reduceQueue', () => {
    it('enqueues a pending entry', () => {
      const state = reduceQueue(emptyQueue(), {
        type: 'enqueue',
        incident: dummyIncident,
        now: 10_000,
      });
      expect(state.entries).toHaveLength(1);
      expect(state.entries[0]!.status).toBe('pending');
      expect(state.entries[0]!.attempts).toBe(0);
      expect(state.entries[0]!.nextAt).toBe(10_000);
    });

    it('deduplicates: ignores enqueuing an existing pending or already sent id', () => {
      const initial: QueueState = {
        entries: [{ incident: dummyIncident, status: 'pending', attempts: 0, nextAt: 10_000 }],
        sent: ['sent-uuid'],
      };

      // Already pending
      const dupPending = reduceQueue(initial, {
        type: 'enqueue',
        incident: dummyIncident,
        now: 12_000,
      });
      expect(dupPending.entries).toHaveLength(1);

      // Already sent
      const dupSent = reduceQueue(initial, {
        type: 'enqueue',
        incident: { ...dummyIncident, client_id: 'sent-uuid' },
        now: 12_000,
      });
      expect(dupSent.entries).toHaveLength(1);
    });

    it('removes the entry and adds to sent on "sent"', () => {
      const initial: QueueState = {
        entries: [{ incident: dummyIncident, status: 'pending', attempts: 1, nextAt: 10_000 }],
        sent: [],
      };
      const after = reduceQueue(initial, {
        type: 'sent',
        clientId: dummyIncident.client_id,
        now: 11_000,
      });
      expect(after.entries).toHaveLength(0);
      expect(after.sent).toEqual([dummyIncident.client_id]);
    });

    it('marks failed and advances nextAt on "failed"', () => {
      const initial: QueueState = {
        entries: [{ incident: dummyIncident, status: 'pending', attempts: 0, nextAt: 10_000 }],
        sent: [],
      };
      const after = reduceQueue(initial, {
        type: 'failed',
        clientId: dummyIncident.client_id,
        now: 10_000,
      });
      expect(after.entries[0]!.status).toBe('failed');
      expect(after.entries[0]!.attempts).toBe(1);
      expect(after.entries[0]!.nextAt).toBe(12_000); // 10_000 + 2_000
    });
  });

  describe('createIncidentQueue lifecycle with fake clock and send', () => {
    it('retries with exponential backoff on failure, then removes on success', async () => {
      let clock = 100_000;
      let shouldSucceed = false;
      const sendCalls: QueuedIncident[] = [];
      const send = async (inc: QueuedIncident) => {
        sendCalls.push(inc);
        return shouldSucceed;
      };

      const storage = memoryStorage();
      const persistence: QueuePersistence = queuePersistence(storage);
      const queue = createIncidentQueue({ send, now: () => clock, persistence });

      await queue.enqueue(dummyIncident);
      expect(queue.getState().entries).toHaveLength(1);

      // 1st flush: fails
      await queue.flush();
      expect(sendCalls).toHaveLength(1);
      expect(queue.getState().entries[0]!.status).toBe('failed');
      expect(queue.getState().entries[0]!.attempts).toBe(1);
      expect(queue.getState().entries[0]!.nextAt).toBe(102_000); // clock + 2s

      // Flush before nextAt: skipped
      clock = 101_000;
      await queue.flush();
      expect(sendCalls).toHaveLength(1);

      // Advance clock to nextAt: 2nd attempt fails
      clock = 102_000;
      await queue.flush();
      expect(sendCalls).toHaveLength(2);
      expect(queue.getState().entries[0]!.attempts).toBe(2);
      expect(queue.getState().entries[0]!.nextAt).toBe(106_000); // clock + 4s

      // Advance to 3rd attempt: success!
      clock = 106_000;
      shouldSucceed = true;
      await queue.flush();
      expect(sendCalls).toHaveLength(3);
      expect(queue.getState().entries).toHaveLength(0);
      expect(queue.getState().sent).toContain(dummyIncident.client_id);
    });

    it('survives app restart via persistence round-trip', async () => {
      let clock = 200_000;
      const storage = memoryStorage();

      // App run 1: enqueue and fail once
      const queue1 = createIncidentQueue({
        send: async () => false,
        now: () => clock,
        persistence: queuePersistence(storage),
      });
      await queue1.enqueue(dummyIncident);
      await queue1.flush();
      expect(queue1.getState().entries[0]!.attempts).toBe(1);

      // App restarts: new instance using the same persistent storage
      const send2 = jest.fn().mockResolvedValue(true);
      const queue2 = createIncidentQueue({
        send: send2,
        now: () => clock + 5_000,
        persistence: queuePersistence(storage),
      });

      // Advance clock past the retry delay and flush
      clock += 5_000;
      await queue2.flush();

      expect(send2).toHaveBeenCalledWith(dummyIncident);
      expect(queue2.getState().entries).toHaveLength(0);
      expect(queue2.getState().sent).toContain(dummyIncident.client_id);
    });
  });
});
