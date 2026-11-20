import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { create } from 'zustand';

export type Contact = { id: string; name: string; phone: string };
export type WifiCredentials = { ssid: string; password: string };

const CONTACTS = 'sahi.contacts';
const WIFI = 'sahi.wifi';

// Web has no keystore: localStorage keeps the UI checkable in a browser.
const read = (k: string) =>
  Platform.OS === 'web' ? (globalThis.localStorage?.getItem(k) ?? null) : SecureStore.getItem(k);
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
    set({ contacts: [], wifi: null });
  },
}));
