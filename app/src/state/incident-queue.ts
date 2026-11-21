import type { StateStorage } from 'zustand/middleware';
import { emptyQueue, type QueuePersistence, type QueueState } from '@/services/incident-queue';

const KEY = 'sahi.incident-queue';
/** Same SQLite KV boundary as settings; injectable for restart tests. */
export function queuePersistence(storage: StateStorage): QueuePersistence {
  return {
    async load() {
      const raw = await storage.getItem(KEY);
      if (!raw) return emptyQueue();
      try {
        const value = JSON.parse(raw) as QueueState;
        if (!Array.isArray(value.entries) || !Array.isArray(value.sent)) return emptyQueue();
        return value;
      } catch {
        return emptyQueue();
      }
    },
    async save(state) { await storage.setItem(KEY, JSON.stringify(state)); },
  };
}
