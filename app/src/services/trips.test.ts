import { parseAlert, parsePhysio, parseStatus } from '@/pi/parse';
import { db } from '@/state/db';
import { INITIAL_LIVE, setLive, useLive } from '@/state/live';
import { useSettings } from '@/state/settings';

import { startTripManager } from './trips';

jest.mock('@/state/db', () => jest.requireActual('@/state/db.web'));
jest.mock('expo-sqlite/kv-store', () => ({ Storage: {
  getItemSync: () => null, setItemSync: jest.fn(), removeItemSync: jest.fn(),
} }));

let stop: () => void;
beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(1800000000000);
  db.wipe();
  useSettings.getState().reset();
  useLive.setState(INITIAL_LIVE);
  stop = startTripManager();
});
afterEach(() => { stop(); jest.useRealTimers(); });

test.each(['phone', 'pi', undefined] as const)('records %s timestamps for HR, alerts and states', (t_src) => {
  const t = 1795189202.4567;
  setLive({ connection: 'online',
    status: parseStatus({ fps: 10, face: true, t, t_src, drowsiness: { state: 'drowsy' } }),
    alert: parseAlert({ pattern: 'max', reasons: [], t, t_src }),
    physio: parsePhysio({ watch_connected: true, hr_bpm: 70, t, t_src }),
  });
  const id = db.openTrip()!.id;
  const at = t_src === 'phone' ? Math.round(t * 1000) : Date.now();
  expect(db.hr(id)).toEqual([expect.objectContaining({ t: at, bpm: 70 })]);
  expect(db.events(id).map((e) => [e.kind, e.t])).toEqual([['state', at], ['alert', at]]);
});

test('HR consent defaults on and off prevents future storage, including timer ticks', () => {
  expect(useSettings.getState().saveTripHeartRate).toBe(true);
  useSettings.getState().set({ saveTripHeartRate: false });
  setLive({ connection: 'online', physio: parsePhysio({ watch_connected: true, hr_bpm: 70, t: 1 }) });
  const id = db.openTrip()!.id;
  jest.advanceTimersByTime(60000);
  expect(db.hr(id)).toEqual([]);
  useSettings.getState().set({ saveTripHeartRate: true });
  setLive({ physio: parsePhysio({ watch_connected: true, hr_bpm: 72, t: 2 }) });
  expect(db.hr(id)).toHaveLength(1);
});
