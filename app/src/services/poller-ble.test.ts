import { setBleLinkForTest } from '@/pi/ble';
import { FakeBleLink } from '@/pi/ble/fake-link';
import { INITIAL_LIVE, setLive, useLive } from '@/state/live';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';

import { startPoller } from './poller';

jest.mock('expo-sqlite/kv-store', () => ({
  Storage: { getItemSync: jest.fn(() => null), setItemSync: jest.fn(), removeItemSync: jest.fn(), clearSync: jest.fn() },
}));
jest.mock('expo-secure-store', () => ({
  getItem: jest.fn(() => null),
  setItem: jest.fn(),
  deleteItemAsync: jest.fn(async () => {}),
}));

const STATUS = { fps: 14, face: true, state: 'alert', baseline: 1, levels: {}, ms: {} };
const ALERT = { pattern: 'none', reasons: [], t: 1 };
const PHYSIO = { watch_connected: true, hr_bpm: 70, rr_ms: [], quality: 'good', t: 1 };
const BODIES: Record<string, unknown> = { '/status': STATUS, '/alert': ALERT, '/physio': PHYSIO };

const link = new FakeBleLink();
let fetchMock: jest.Mock;
const calls = (path: string) => fetchMock.mock.calls.filter(([url]) => String(url).endsWith(path)).length;
const tick = (ms: number) => jest.advanceTimersByTimeAsync(ms);

beforeEach(() => {
  jest.useFakeTimers();
  link.setState('idle');
  link.lastNotifyAt = null;
  setBleLinkForTest(link);
  useSettings.getState().reset();
  useSettings.getState().set({ bleName: 'RTDMS-Pi', baseUrl: 'http://pi.test:8080' });
  useSecure.getState().setPiToken('k3Jx9mQ2pL7vN4wR8tY1');
  useLive.setState(INITIAL_LIVE);
  fetchMock = jest.fn(async (url: string) => ({
    ok: true,
    json: async () => BODIES[new URL(url).pathname],
  }));
  global.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  jest.useRealTimers();
  setBleLinkForTest(null);
});

describe('poller over Bluetooth', () => {
  it('sends no HTTP while the link is online and fills useLive from notifications', async () => {
    link.setState('online');
    const stop = startPoller();
    link.emit('status', STATUS);
    link.emit('alert', { pattern: 'repeated', reasons: ['eyes closed'], t: 2 });
    link.emit('physio', PHYSIO);
    for (let i = 0; i < 10; i++) {
      await tick(1000);
      link.emit('status', { ...STATUS, fps: 14 + (i % 2) });
    }
    expect(fetchMock).not.toHaveBeenCalled();
    const live = useLive.getState();
    expect(live).toMatchObject({ connection: 'online', link: 'ble', alertSupported: true, physioSupported: true });
    expect(live.alert?.pattern).toBe('repeated');
    expect(live.physio?.hr_bpm).toBe(70);
    stop();
  });

  it('writes useLive once per changed value, not for identical repeats', async () => {
    link.setState('online');
    const stop = startPoller();
    const seen = jest.fn();
    const off = useLive.subscribe(seen);
    link.emit('status', STATUS);
    expect(seen).toHaveBeenCalledTimes(1); // first notify: status + connection/link in one write
    link.emit('status', STATUS);
    link.emit('status', { ...STATUS });
    expect(seen).toHaveBeenCalledTimes(1);
    link.emit('status', { ...STATUS, fps: 9 });
    expect(seen).toHaveBeenCalledTimes(2);
    link.emit('alert', ALERT);
    link.emit('alert', ALERT);
    expect(seen).toHaveBeenCalledTimes(3);
    off();
    stop();
  });

  it('ignores alert timestamp heartbeats but keeps the link fresh', async () => {
    link.setState('online');
    const stop = startPoller();
    link.emit('alert', ALERT);
    const seen = jest.fn();
    const off = useLive.subscribe(seen);
    for (let t = 2; t <= 8; t++) {
      await tick(1000);
      link.emit('alert', { ...ALERT, t });
    }
    expect(seen).not.toHaveBeenCalled();
    expect(useLive.getState().connection).toBe('online');
    expect(link.lastNotifyAt).toBe(Date.now());
    link.emit('alert', { ...ALERT, reasons: ['changed'], t: 9 });
    expect(seen).toHaveBeenCalledTimes(1);
    off();
    stop();
  });

  it('publishes emergency changes even when pattern and reasons stay unchanged', () => {
    link.setState('online');
    const stop = startPoller();
    link.emit('alert', ALERT);
    link.emit('alert', { ...ALERT, emergency: 'unresponsive' });
    expect(useLive.getState().alert?.emergency).toBe('unresponsive');
    link.emit('alert', ALERT);
    expect(useLive.getState().alert?.emergency).toBeUndefined();
    stop();
  });

  it('never writes lastOkAt per notify', async () => {
    link.setState('online');
    const stop = startPoller();
    link.emit('status', STATUS);
    const first = useLive.getState().lastOkAt;
    await tick(500);
    link.emit('status', { ...STATUS, fps: 8 });
    expect(useLive.getState().lastOkAt).toBe(first);
    stop();
  });

  it('goes offline after 3 s without a notify and recovers on the next one', async () => {
    link.setState('online');
    const stop = startPoller();
    link.emit('status', STATUS);
    link.emit('alert', { pattern: 'repeated', reasons: [], t: 1 });
    await tick(2900);
    expect(useLive.getState().connection).toBe('online');
    await tick(200);
    expect(useLive.getState()).toMatchObject({ connection: 'offline', alert: null, physio: null });
    expect(fetchMock).not.toHaveBeenCalled();
    link.emit('status', STATUS);
    expect(useLive.getState().connection).toBe('online');
    stop();
  });

  it('keeps the timeout alive while notifies keep arriving', async () => {
    link.setState('online');
    const stop = startPoller();
    for (let i = 0; i < 8; i++) {
      link.emit('status', { ...STATUS, fps: i });
      await tick(1000);
    }
    expect(useLive.getState().connection).toBe('online');
    expect(jest.getTimerCount()).toBe(1);
    stop();
  });

  it('falls back to HTTP at 1 Hz when the link drops, and stops it when the link is back', async () => {
    link.setState('online');
    const stop = startPoller();
    link.emit('status', STATUS);
    link.setState('offline');
    await tick(3500);
    expect(calls('/status')).toBeGreaterThanOrEqual(3);
    expect(calls('/status')).toBeLessThanOrEqual(4); // 1 Hz, not 5 Hz
    expect(useLive.getState()).toMatchObject({ connection: 'online', link: 'http' });

    link.setState('online');
    await tick(50);
    fetchMock.mockClear();
    link.emit('status', { ...STATUS, fps: 3 });
    await tick(5000);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(useLive.getState().link).toBe('ble');
    stop();
  });

  it('polls HTTP at 1 Hz from the start when the link is not online yet', async () => {
    link.setState('scanning');
    const stop = startPoller();
    await tick(3500);
    expect(calls('/status')).toBeLessThanOrEqual(4);
    stop();
  });

  it('keeps the 5 Hz poll when there is no Bluetooth pairing', async () => {
    useSettings.getState().set({ bleName: null });
    const stop = startPoller();
    await tick(1000);
    expect(calls('/status')).toBeGreaterThanOrEqual(4);
    expect(useLive.getState().link).toBe('http');
    stop();
  });

  it('leaves no timers behind after the cleanup', async () => {
    link.setState('online');
    const stop = startPoller();
    link.emit('status', STATUS);
    expect(jest.getTimerCount()).toBe(1);
    stop();
    expect(jest.getTimerCount()).toBe(0);

    link.setState('offline');
    const stop2 = startPoller();
    await tick(1500);
    stop2();
    await tick(10);
    expect(jest.getTimerCount()).toBe(0);
    setLive({ connection: 'connecting' });
  });
});
