import { db } from '@/state/db';
import { setLive, useLive, INITIAL_LIVE } from '@/state/live';
import { parsePhysio } from '@/pi/parse';

import { isWatchAckFresh, startWatchAckCancel, WATCH_ACK_FRESH_S } from './watch-ack-cancel';

jest.mock('expo-router', () => ({ router: { push: jest.fn(), back: jest.fn() } }));
jest.mock('./incident-delivery', () => ({
  incidentClientId: () => 'test',
  incidentQueue: { enqueue: jest.fn(async () => {}), flush: jest.fn(async () => {}) },
}));
jest.mock('./trips', () => ({ currentTripId: () => null }));
jest.mock('@modules/sahi-native', () => ({ __esModule: true, default: null }));

const physio = (ack_age_s: number | null) =>
  parsePhysio({
    watch_connected: true,
    hr_bpm: 70,
    worn: true,
    ack_age_s,
    t: 1,
    t_src: 'phone',
  })!;

beforeEach(() => {
  useLive.setState(INITIAL_LIVE);
  jest.spyOn(db, 'incidents').mockReturnValue([]);
  jest.spyOn(db, 'saveIncident').mockImplementation(() => {});
  jest.spyOn(db, 'addIncident').mockReturnValue(42);
  jest.spyOn(db, 'addEvent').mockImplementation(() => {});
});

afterEach(() => {
  jest.restoreAllMocks();
});

test('fresh ack cancels pending SOS once', () => {
  const save = jest.mocked(db.saveIncident);
  jest.mocked(db.incidents).mockReturnValue([{ id: 7, outcome: 'pending' }] as ReturnType<typeof db.incidents>);
  const stop = startWatchAckCancel();
  setLive({ physio: physio(0.4) });
  expect(save).toHaveBeenCalledWith(7, { outcome: 'cancelled' });
  save.mockClear();
  setLive({ physio: physio(0.8) }); // still fresh: no second cancel
  expect(save).not.toHaveBeenCalled();
  setLive({ physio: physio(5) }); // ages out → re-arm
  setLive({ physio: physio(0.1) });
  expect(save).toHaveBeenCalledWith(7, { outcome: 'cancelled' });
  stop();
});

test('isWatchAckFresh matches Pi threshold', () => {
  expect(WATCH_ACK_FRESH_S).toBe(2);
  expect(isWatchAckFresh(0)).toBe(true);
  expect(isWatchAckFresh(2)).toBe(true);
  expect(isWatchAckFresh(2.01)).toBe(false);
  expect(isWatchAckFresh(null)).toBe(false);
});
