import { CrashMonitor } from '@/crash/detector';
import { parsePhysio } from '@/pi/parse';
import { INITIAL_LIVE, setLive, useLive } from '@/state/live';
import { useSettings } from '@/state/settings';

import { startMonitor } from './monitor';

jest.mock('@modules/sahi-native', () => null);
jest.mock('expo-location', () => ({
  getForegroundPermissionsAsync: async () => ({ granted: false }),
  hasStartedLocationUpdatesAsync: async () => false,
}));
jest.mock('expo-task-manager', () => ({ defineTask: jest.fn() }));
jest.mock('expo-sqlite/kv-store', () => ({ Storage: {
  getItemSync: () => null, setItemSync: jest.fn(), removeItemSync: jest.fn(),
} }));
jest.mock('./pi', () => ({ pi: jest.fn() }));
jest.mock('./emergency', () => ({ triggerSos: jest.fn() }));
jest.mock('./unresponsive', () => ({ startUnresponsiveMonitor: () => () => {} }));
jest.mock('./watch-ack-cancel', () => ({ startWatchAckCancel: () => () => {} }));

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(1800000000000);
  useLive.setState(INITIAL_LIVE);
  useSettings.getState().reset();
});
afterEach(() => { jest.useRealTimers(); jest.restoreAllMocks(); });

test.each(['phone', 'pi', undefined] as const)('last-minute HR evidence uses %s time', (t_src) => {
  const check = jest.spyOn(CrashMonitor.prototype, 'check').mockReturnValue(null);
  const stop = startMonitor();
  const arrival = Date.now();
  const t = (arrival - 2000) / 1000 + 0.0007;
  setLive({ physioSupported: true, physio: parsePhysio({ watch_connected: true, hr_bpm: 71, t, t_src }) });
  jest.advanceTimersByTime(500);
  expect(check.mock.calls.at(-1)?.[1]?.hr).toContainEqual({
    t: t_src === 'phone' ? Math.round(t * 1000) : arrival, bpm: 71,
  });
  jest.advanceTimersByTime(61000);
  expect(check.mock.calls.at(-1)?.[1]?.hr).toEqual([]);
  stop();
});
