import { Storage } from 'expo-sqlite/kv-store';
import type { StateStorage } from 'zustand/middleware';

/** Synchronous on-device key-value storage (SQLite), so settings are ready on the first frame. */
export const kv: StateStorage = {
  getItem: (k) => Storage.getItemSync(k),
  setItem: (k, v) => Storage.setItemSync(k, v),
  removeItem: (k) => void Storage.removeItemSync(k),
};

export function clearKv(): void {
  Storage.clearSync();
}
