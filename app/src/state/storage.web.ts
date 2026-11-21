import type { StateStorage } from 'zustand/middleware';

// Web build (screenshots / quick UI checks only): localStorage instead of SQLite.
export const kv: StateStorage = {
  getItem: (k) => globalThis.localStorage?.getItem(k) ?? null,
  setItem: (k, v) => globalThis.localStorage?.setItem(k, v),
  removeItem: (k) => globalThis.localStorage?.removeItem(k),
};

export function clearKv(): void {
  globalThis.localStorage?.clear();
}
