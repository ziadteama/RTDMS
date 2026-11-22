import { DEFAULT_SETTINGS, type EyeCalibration, useSettings } from './settings';

const mockStore = new Map<string, string>();

jest.mock('expo-sqlite/kv-store', () => ({
  Storage: {
    getItemSync: jest.fn((k: string) => mockStore.get(k) ?? null),
    setItemSync: jest.fn((k: string, v: string) => mockStore.set(k, v)),
    removeItemSync: jest.fn((k: string) => mockStore.delete(k)),
    clearSync: jest.fn(() => mockStore.clear()),
  },
}));

describe('useSettings store - eyeCalibration', () => {
  beforeEach(() => {
    mockStore.clear();
    useSettings.getState().reset();
  });

  it('defaults to null', () => {
    expect(useSettings.getState().eyeCalibration).toBeNull();
  });

  it('updates eyeCalibration via setEyeCalibration action and set', () => {
    const cal: EyeCalibration = {
      closedRatio: 0.38,
      earOpen: 0.29,
      earClosed: 0.11,
      snr: 46.2,
      quality: 'good',
      at: 1795189202400,
      syncedAt: null,
    };

    useSettings.getState().setEyeCalibration(cal);
    expect(useSettings.getState().eyeCalibration).toEqual(cal);

    useSettings.getState().set({ eyeCalibration: null });
    expect(useSettings.getState().eyeCalibration).toBeNull();
  });

  it('resets eyeCalibration to null on reset()', () => {
    const cal: EyeCalibration = {
      closedRatio: 0.38,
      earOpen: 0.29,
      earClosed: 0.11,
      snr: 46.2,
      quality: 'good',
      at: 1795189202400,
      syncedAt: 1795189205000,
    };

    useSettings.getState().setEyeCalibration(cal);
    expect(useSettings.getState().eyeCalibration).not.toBeNull();

    useSettings.getState().reset();
    expect(useSettings.getState().eyeCalibration).toBeNull();
  });

  it('whitelists eyeCalibration in merge and filters out obsolete fields', () => {
    const cal: EyeCalibration = {
      closedRatio: 0.35,
      earOpen: 0.3,
      earClosed: 0.1,
      snr: 40,
      quality: 'good',
      at: 1234567,
      syncedAt: null,
    };

    const persistOptions = (
      useSettings as unknown as {
        persist: {
          getOptions: () => {
            merge: (persisted: unknown, current: unknown) => unknown;
          };
        };
      }
    ).persist.getOptions();

    const persisted = {
      eyeCalibration: cal,
      obsoleteField: 'should_be_dropped',
      theme: 'light',
    };

    const current = { ...DEFAULT_SETTINGS };
    const merged = persistOptions.merge(persisted, current) as typeof DEFAULT_SETTINGS & {
      obsoleteField?: string;
    };

    expect(merged.eyeCalibration).toEqual(cal);
    expect(merged.theme).toBe('light');
    expect(merged.obsoleteField).toBeUndefined();
  });
});
