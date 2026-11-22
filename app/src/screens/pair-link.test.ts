import { FakeBleLink } from '@/pi/ble/fake-link';

import { firstTrue, waitBleOnline } from './pair-link';

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
