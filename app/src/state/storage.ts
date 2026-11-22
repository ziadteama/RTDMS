import { Storage } from 'expo-sqlite/kv-store';
import type { StateStorage } from 'zustand/middleware';

const inMemory = new Map<string, string>();

/** Synchronous on-device key-value storage (SQLite), so settings are ready on the first frame. */
export const kv: StateStorage = {
  getItem: (k) => {
    try {
      return Storage.getItemSync(k);
    } catch {
      return inMemory.get(k) ?? null;
    }
  },
  setItem: (k, v) => {
    try {
      Storage.setItemSync(k, v);
    } catch {
      inMemory.set(k, v);
    }
  },
  removeItem: (k) => {
    try {
      Storage.removeItemSync(k);
    } catch {
      inMemory.delete(k);
    }
  },
};

export function clearKv(): void {
  try {
    Storage.clearSync();
  } catch {
    inMemory.clear();
  }
}
