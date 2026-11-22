import { parseAlert } from '@/pi/parse';
import { INITIAL_LIVE, setLive, useLive } from '@/state/live';
import { db } from '@/state/db';

import { triggerSos } from './emergency';
import { startUnresponsiveMonitor } from './unresponsive';

jest.mock('./emergency', () => ({ triggerSos: jest.fn() }));
jest.mock('@/state/db', () => ({ db: { incidents: jest.fn(() => []) } }));
const alert = (emergency?: 'unresponsive') => parseAlert({ pattern: 'max', reasons: [], t: 1, emergency });
beforeEach(() => { jest.clearAllMocks(); useLive.setState(INITIAL_LIVE); });

test('fires once per episode, including after cancellation or an offline gap', () => {
  const stop = startUnresponsiveMonitor();
  setLive({ connection: 'online', alert: alert('unresponsive') });
  setLive({ alert: alert('unresponsive') });
  setLive({ connection: 'offline', alert: null });
  setLive({ connection: 'online', alert: alert('unresponsive') });
  expect(triggerSos).toHaveBeenCalledTimes(1);
  expect(triggerSos).toHaveBeenCalledWith('unresponsive');
  setLive({ alert: alert() });
  setLive({ alert: alert('unresponsive') });
  expect(triggerSos).toHaveBeenCalledTimes(2);
  stop();
});

test('does not start another unresponsive SOS while one is pending', () => {
  jest.mocked(db.incidents).mockReturnValueOnce([{ kind: 'unresponsive', outcome: 'pending' }] as ReturnType<typeof db.incidents>);
  setLive({ connection: 'online', alert: alert('unresponsive') });
  const stop = startUnresponsiveMonitor();
  expect(triggerSos).not.toHaveBeenCalled();
  stop();
});
