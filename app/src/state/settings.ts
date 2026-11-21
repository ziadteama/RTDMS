import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { kv } from './storage';

export const DEFAULT_BASE_URL = 'http://10.42.0.1:8080';

export type ThemeSetting = 'dark' | 'light' | 'system';
export type Units = 'kmh' | 'mph';
export type Vibration = 'off' | 'light' | 'strong';
export type CallTarget = 'ambulance' | 'contact';

/** App-side settings only. Detection thresholds live on the Pi (GET / PUT /settings). */
export type Settings = {
  consentedAt: number | null;
  onboarded: boolean;
  theme: ThemeSetting;
  units: Units;
  baseUrl: string;
  demo: boolean;
  paused: boolean;
  sound: boolean;
  volume: number;
  vibration: Vibration;
  crashDetection: boolean;
  callTarget: CallTarget;
  ambulanceNumber: string;
};

export const DEFAULT_SETTINGS: Settings = {
  consentedAt: null,
  onboarded: false,
  theme: 'dark',
  units: 'kmh',
  baseUrl: DEFAULT_BASE_URL,
  demo: false,
  paused: false,
  sound: true,
  volume: 1,
  vibration: 'strong',
  crashDetection: true,
  callTarget: 'ambulance',
  ambulanceNumber: '123',
};

type SettingsStore = Settings & {
  set: (patch: Partial<Settings>) => void;
  reset: () => void;
};

export const useSettings = create<SettingsStore>()(
  persist(
    (set) => ({
      ...DEFAULT_SETTINGS,
      set: (patch) => set(patch),
      reset: () => set(DEFAULT_SETTINGS),
    }),
    {
      name: 'sahi.settings', version: 1, storage: createJSONStorage(() => kv),
      // Load only current settings, ignoring obsolete persisted fields.
      merge: (persisted, current) => ({
        ...current,
        ...Object.fromEntries(Object.entries((persisted ?? {}) as Record<string, unknown>)
          .filter(([key]) => Object.hasOwn(DEFAULT_SETTINGS, key))),
      }),
    },
  ),
);
