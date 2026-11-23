import * as Haptics from 'expo-haptics';
import * as Speech from 'expo-speech';
import { AppState } from 'react-native';
import SahiNative from '@modules/sahi-native';
import { parseAlert } from '@/pi/parse';
import type { AlertPattern } from '@/pi/types';
import { INITIAL_LIVE, setLive, useLive } from '@/state/live';
import { speak, startAlertEngine } from './alerts';

jest.mock('expo-haptics', () => ({ impactAsync: jest.fn(), notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Heavy: 'heavy' }, NotificationFeedbackType: { Warning: 'warning', Error: 'error' } }));
jest.mock('expo-speech', () => ({ stop: jest.fn().mockResolvedValue(undefined), speak: jest.fn() }));
jest.mock('@modules/sahi-native', () => ({ __esModule: true, default: { notify: jest.fn(), cancel: jest.fn() } }));
jest.mock('@/state/settings', () => ({ useSettings: { getState: () => ({ sound: true, volume: 1, vibration: 'strong' }) } }));
const send = (pattern: AlertPattern, episode: number | null = 1) =>
  setLive({ connection: 'online', alert: parseAlert({ pattern, episode, reasons: [], t: Date.now() }) });
const flush = async () => { await Promise.resolve(); };
let stop: () => void;
beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  AppState.currentState = 'background';
  useLive.setState(INITIAL_LIVE);
  stop = startAlertEngine();
});
afterEach(() => { stop(); jest.useRealTimers(); });

test('many notifies and keep-alives present once, escalation and new episodes present again', async () => {
  send('short_beep');
  for (let i = 0; i < 20; i++) { send('short_beep'); setLive({ lastOkAt: i }); }
  await flush();
  expect(Speech.speak).toHaveBeenCalledTimes(1);
  expect(Haptics.impactAsync).toHaveBeenCalledTimes(1);
  expect(SahiNative?.notify).toHaveBeenCalledTimes(1);
  send('continuous'); await flush();
  send('continuous'); await flush();
  expect(Speech.speak).toHaveBeenCalledTimes(2);
  send('continuous', 2); await flush();
  expect(Speech.speak).toHaveBeenCalledTimes(3);
  send('none', 2);
  expect(SahiNative?.cancel).toHaveBeenCalledTimes(1);
  expect(Speech.stop).toHaveBeenCalledTimes(4);
  send('short_beep', 3); await flush();
  expect(Speech.speak).toHaveBeenCalledTimes(4);
});

test.each(['repeated', 'continuous', 'max'] as const)('%s retains haptic cadence with voice no faster than 8 seconds', async (pattern) => {
  send(pattern); await flush();
  const cadence = { repeated: 8000, continuous: 5000, max: 4000 }[pattern];
  let voices = 1;
  let lastVoice = 0;
  for (let elapsed = cadence; elapsed <= 40000; elapsed += cadence) {
    jest.advanceTimersByTime(cadence); await flush();
    const calls = jest.mocked(Speech.speak).mock.calls.length;
    if (calls > voices) { expect(elapsed - lastVoice).toBeGreaterThanOrEqual(8000); lastVoice = elapsed; voices = calls; }
  }
  expect(voices).toBeGreaterThan(1);
  expect(Haptics.notificationAsync).toHaveBeenCalledTimes(1 + Math.floor(40000 / cadence));
  expect(SahiNative?.notify).toHaveBeenCalledTimes(1);
});

test('awaits stop before speaking and discards superseded or ended requests', async () => {
  let resolve!: () => void;
  jest.mocked(Speech.stop).mockImplementationOnce(() => new Promise<void>((done) => { resolve = done; }));
  speak('voice.generic');
  expect(Speech.speak).not.toHaveBeenCalled();
  speak('voice.max'); await flush();
  resolve(); await flush();
  expect(Speech.speak).toHaveBeenCalledTimes(1);
  const speechOrder = jest.mocked(Speech.speak).mock.invocationCallOrder[0]!;
  expect(jest.mocked(Speech.stop).mock.invocationCallOrder[1]).toBeLessThan(speechOrder);
  send('max'); send('none'); await flush();
  expect(Speech.speak).toHaveBeenCalledTimes(1);
});

test('calibration immediately stops output and silences all alert updates and repeats', async () => {
  send('max'); await flush();
  setLive({ calibrating: true });
  expect(SahiNative?.cancel).toHaveBeenCalledTimes(1);
  jest.clearAllMocks();
  send('max', 2); send('continuous', 3);
  jest.advanceTimersByTime(30000); await flush();
  expect(Speech.speak).not.toHaveBeenCalled();
  expect(Haptics.notificationAsync).not.toHaveBeenCalled();
  expect(SahiNative?.notify).not.toHaveBeenCalled();
  setLive({ calibrating: false }); await flush();
  expect(Speech.speak).toHaveBeenCalledTimes(1);
});

test('null episodes use escalation only', async () => {
  send('continuous', null); await flush();
  send('continuous', null); send('repeated', null); await flush();
  expect(Speech.speak).toHaveBeenCalledTimes(1);
  send('continuous', null); await flush();
  expect(Speech.speak).toHaveBeenCalledTimes(2);
  send('none', null); send('short_beep', null); await flush();
  expect(Speech.speak).toHaveBeenCalledTimes(3);
});
