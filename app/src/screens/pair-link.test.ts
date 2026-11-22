import { FakeBleLink } from '@/pi/ble/fake-link';

import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';

import { firstTrue, pairOpen, waitBleOnline } from './pair-link';

jest.mock('expo-sqlite/kv-store', () => ({
  Storage: { getItemSync: jest.fn(() => null), setItemSync: jest.fn(), removeItemSync: jest.fn(), clearSync: jest.fn() },
}));
jest.mock('expo-secure-store', () => ({
  getItem: jest.fn(() => null),
  setItem: jest.fn(),
  deleteItemAsync: jest.fn(async () => {}),
}));

describe('waitBleOnline', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it('resolves true when the link comes online and leaves no timer or subscription', async () => {
    const link = new FakeBleLink();
    link.setState('scanning');
    const { done } = waitBleOnline(link);
    link.setState('online');
    await expect(done).resolves.toBe(true);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('resolves true at once when already online', async () => {
    const link = new FakeBleLink();
    link.setState('online');
    await expect(waitBleOnline(link).done).resolves.toBe(true);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('resolves false after 10 s', async () => {
    const link = new FakeBleLink();
    link.setState('scanning');
    const { done } = waitBleOnline(link);
    await jest.advanceTimersByTimeAsync(9999);
    link.setState('connecting');
    await jest.advanceTimersByTimeAsync(1);
    await expect(done).resolves.toBe(false);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('cancel() clears the timer', async () => {
    const link = new FakeBleLink();
    link.setState('scanning');
    const w = waitBleOnline(link);
    w.cancel();
    expect(jest.getTimerCount()).toBe(0);
    await expect(w.done).resolves.toBe(false);
  });
});

describe('firstTrue', () => {
  it('is true when any check passes, false when all fail or none', async () => {
    await expect(firstTrue([Promise.resolve(false), Promise.resolve(true)])).resolves.toBe(true);
    await expect(firstTrue([Promise.resolve(false), Promise.resolve(false)])).resolves.toBe(false);
    await expect(firstTrue([])).resolves.toBe(false);
  });
});

describe('pairOpen', () => {
  const unit = { id: 'dev-9', name: 'RTDMS-Pi', rssi: -50 };
  beforeEach(() => {
    useSettings.getState().reset();
    useSecure.getState().wipe();
  });

  it('saves the unit with NO token and resolves ok when the link comes online', async () => {
    const link = new FakeBleLink();
    const p = pairOpen(unit, link);
    expect(useSettings.getState().bleName).toBe('RTDMS-Pi');
    expect(useSettings.getState().bleDeviceId).toBe('dev-9');
    expect(useSecure.getState().piToken).toBeNull();
    link.setState('online');
    await expect(p).resolves.toBe('ok');
    expect(useSettings.getState().bleName).toBe('RTDMS-Pi');
  });

  it('when the unit rejects (needs a code) returns needs-code at once and restores the old pairing', async () => {
    useSettings.getState().set({ bleName: 'Old-Pi', bleDeviceId: 'old' });
    useSecure.getState().setPiToken('k3Jx9mQ2pL7vN4wR8tY1');
    const link = new FakeBleLink();
    link.setState('scanning');
    const p = pairOpen(unit, link);
    link.lastError = 'auth';
    link.setState('offline');
    await expect(p).resolves.toBe('needs-code');
    expect(useSettings.getState().bleName).toBe('Old-Pi');
    expect(useSettings.getState().bleDeviceId).toBe('old');
    expect(useSecure.getState().piToken).toBe('k3Jx9mQ2pL7vN4wR8tY1');
  });

  it('returns unreachable after the timeout without an auth error', async () => {
    jest.useFakeTimers();
    const link = new FakeBleLink();
    const p = pairOpen(unit, link, 1000);
    await jest.advanceTimersByTimeAsync(1000);
    await expect(p).resolves.toBe('unreachable');
    expect(useSettings.getState().bleName).toBeNull();
    jest.useRealTimers();
  });
});
