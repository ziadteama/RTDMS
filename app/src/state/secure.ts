import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { create } from 'zustand';

export type ContactRegisterStatus = 'pending' | 'ok' | 'opted_out' | 'invalid' | 'failed';
export type Contact = { id: string; name: string; phone: string; relayStatus?: ContactRegisterStatus };
export type WifiCredentials = { ssid: string; password: string };

const CONTACTS = 'sahi.contacts';
const WIFI = 'sahi.wifi';
const INSTALL_ID = 'sahi.install_id';

// Web has no keystore: localStorage keeps the UI checkable in a browser.
const read = (k: string): string | null => {
  if (Platform.OS === 'web') return globalThis.localStorage?.getItem(k) ?? null;
  const val = SecureStore.getItem(k);
  return typeof val === 'string' ? val : null;
};
const write = (k: string, v: string | null) => {
  if (Platform.OS === 'web') {
    if (v === null) globalThis.localStorage?.removeItem(k);
    else globalThis.localStorage?.setItem(k, v);
  } else if (v === null) void SecureStore.deleteItemAsync(k);
  else SecureStore.setItem(k, v);
};

function load<T>(k: string, fallback: T): T {
  try {
    const s = read(k);
    return s ? (JSON.parse(s) as T) : fallback;
  } catch {
    return fallback;
  }
}

type SecureState = {
  contacts: Contact[];
  wifi: WifiCredentials | null;
  setContacts: (c: Contact[]) => void;
  setWifi: (w: WifiCredentials | null) => void;
  wipe: () => void;
};

/** Emergency contacts and the Pi hotspot password: Android Keystore via expo-secure-store. */
export const useSecure = create<SecureState>((set) => ({
  contacts: load<Contact[]>(CONTACTS, []),
  wifi: load<WifiCredentials | null>(WIFI, null),
  setContacts: (contacts) => {
    write(CONTACTS, JSON.stringify(contacts));
    set({ contacts });
  },
  setWifi: (wifi) => {
    write(WIFI, wifi ? JSON.stringify(wifi) : null);
    set({ wifi });
  },
  wipe: () => {
    write(CONTACTS, null);
    write(WIFI, null);
    write(INSTALL_ID, null);
    set({ contacts: [], wifi: null });
  },
}));

function randomUuid(random = Math.random): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const value = Math.floor(random() * 16);
    return (c === 'x' ? value : (value & 3) | 8).toString(16);
  });
}

/** Per-install random UUID v4, created on first run and stored in secure store. */
export function getInstallId(random = Math.random): string {
  const existing = read(INSTALL_ID);
  if (existing) return existing;
  const created = randomUuid(random);
  write(INSTALL_ID, created);
  return created;
}
