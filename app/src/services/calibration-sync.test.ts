import { setLive } from '@/state/live';
import { useSettings } from '@/state/settings';

import {
  type CalibrationSyncStatus,
  type CalibrationTransport,
  clearCalibrationSyncState,
  getCalibrationSyncError,
  lastError,
  startCalibrationSync,
  syncEyeCalibration,
} from './calibration-sync';

const mockKvStore = new Map<string, string>();

jest.mock('expo-sqlite/kv-store', () => ({
  Storage: {
    getItemSync: jest.fn((k: string) => mockKvStore.get(k) ?? null),
    setItemSync: jest.fn((k: string, v: string) => mockKvStore.set(k, v)),
    removeItemSync: jest.fn((k: string) => mockKvStore.delete(k)),
    clearSync: jest.fn(() => mockKvStore.clear()),
  },
}));

describe('calibration-sync', () => {
  const fakeCalibration = {
    closedRatio: 0.38,
    earOpen: 0.29,
    earClosed: 0.11,
    snr: 46.2,
    quality: 'good' as const,
    at: 1795189202400,
    syncedAt: null,
  };

  beforeEach(() => {
    mockKvStore.clear();
    useSettings.getState().reset();
    setLive({ connection: 'online' });
    clearCalibrationSyncState();
  });

  it('syncs successfully (200 ok) and sets syncedAt = now', async () => {
    useSettings.getState().setEyeCalibration({ ...fakeCalibration });

    const sentPayloads: unknown[] = [];
    const transport: CalibrationTransport = {
      send: async (payload) => {
        sentPayloads.push(payload);
        return 'ok';
      },
    };

    const status = await syncEyeCalibration(transport);
    expect(status).toBe('ok');
    expect(sentPayloads).toHaveLength(1);
    expect(sentPayloads[0]).toMatchObject({
      source: 'phone',
      closed_ratio: 0.38,
      ear_open: 0.29,
      ear_closed: 0.11,
      quality: 'good',
    });

    const current = useSettings.getState().eyeCalibration;
    expect(current?.syncedAt).not.toBeNull();
    expect(typeof current?.syncedAt).toBe('number');
    expect(getCalibrationSyncError()).toBeNull();
  });

  it('handles 400 rejected: keeps syncedAt null, exposes lastError, and does not retry same payload', async () => {
    useSettings.getState().setEyeCalibration({ ...fakeCalibration });

    let callCount = 0;
    const transport: CalibrationTransport = {
      send: async () => {
        callCount++;
        return 'rejected';
      },
    };

    const status1 = await syncEyeCalibration(transport);
    expect(status1).toBe('rejected');
    expect(callCount).toBe(1);

    const current = useSettings.getState().eyeCalibration;
    expect(current?.syncedAt).toBeNull();
    expect(getCalibrationSyncError()).toContain('rejected');

    // Second call with same calibration must NOT call transport again
    const status2 = await syncEyeCalibration(transport);
    expect(status2).toBe('rejected');
    expect(callCount).toBe(1); // Not retried!
  });

  it('handles unreachable: retries later on reconnect when connection becomes online', async () => {
    useSettings.getState().setEyeCalibration({ ...fakeCalibration });
    setLive({ connection: 'offline' });

    let sendResult: CalibrationSyncStatus = 'unreachable';
    let callCount = 0;
    const transport: CalibrationTransport = {
      send: async () => {
        callCount++;
        return sendResult;
      },
    };

    // While offline, sync is skipped
    expect(await syncEyeCalibration(transport)).toBe('skipped');
    expect(callCount).toBe(0);

    // Online, but transport returns unreachable (network error)
    setLive({ connection: 'online' });
    expect(await syncEyeCalibration(transport)).toBe('unreachable');
    expect(callCount).toBe(1);
    expect(useSettings.getState().eyeCalibration?.syncedAt).toBeNull();
    expect(lastError).toContain('unreachable');

    // Transition offline before registering subscriber
    setLive({ connection: 'offline' });
    sendResult = 'ok';

    // Wire reconnect subscriber
    const unsub = startCalibrationSync(transport);

    // Transition offline -> online (simulating reconnect)
    setLive({ connection: 'online' });

    // Allow microtasks to resolve
    await new Promise((r) => setTimeout(r, 10));

    expect(callCount).toBe(2);
    expect(useSettings.getState().eyeCalibration?.syncedAt).not.toBeNull();
    expect(getCalibrationSyncError()).toBeNull();

    unsub();
  });

  it('demo mode sends NOTHING and never marks synced', async () => {
    useSettings.getState().set({ demo: true });
    useSettings.getState().setEyeCalibration({ ...fakeCalibration });

    let called = false;
    const transport: CalibrationTransport = {
      send: async () => {
        called = true;
        return 'ok';
      },
    };

    const status = await syncEyeCalibration(transport);
    expect(status).toBe('skipped');
    expect(called).toBe(false);
    expect(useSettings.getState().eyeCalibration?.syncedAt).toBeNull();
  });

  it('already synced is not re-sent', async () => {
    useSettings.getState().setEyeCalibration({
      ...fakeCalibration,
      syncedAt: 1795189205000,
    });

    let called = false;
    const transport: CalibrationTransport = {
      send: async () => {
        called = true;
        return 'ok';
      },
    };

    const status = await syncEyeCalibration(transport);
    expect(status).toBe('skipped');
    expect(called).toBe(false);
  });
});
