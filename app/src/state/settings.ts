import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { emergencySettings, type SosCountdownSeconds } from './emergency-settings';
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
  emergencyNumber: string;
  sosCountdownSeconds: SosCountdownSeconds;
  relayUrl?: string;
  relayKey?: string;
  driverName?: string;
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
  emergencyNumber: '123',
  sosCountdownSeconds: 45,
  relayUrl: undefined,
  relayKey: undefined,
  driverName: 'Driver',
};

type SettingsStore = Settings & {
  set: (patch: Partial<Settings>) => void;
  reset: () => void;
};

export const useSettings = create<SettingsStore>()(
  persist(
    (set) => ({
      ...DEFAULT_SETTINGS,
      set: (patch) => {
        const { emergencyNumber: _number, sosCountdownSeconds: _seconds, ...rest } = patch;
        set({ ...rest, ...emergencySettings(patch) });
      },
      reset: () => set(DEFAULT_SETTINGS),
    }),
    {
      name: 'sahi.settings', version: 1, storage: createJSONStorage(() => kv),
      // Load only current settings, ignoring obsolete persisted fields.
      merge: (persisted, current) => ({
        ...current,
        ...Object.fromEntries(Object.entries((persisted ?? {}) as Record<string, unknown>)
          .filter(([key]) => Object.hasOwn(DEFAULT_SETTINGS, key) && !['emergencyNumber', 'sosCountdownSeconds'].includes(key))),
        ...emergencySettings((persisted ?? {}) as Record<string, unknown>),
      }),
    },
  ),
);
