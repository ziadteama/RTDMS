import { act, fireEvent, render, renderHook } from '@testing-library/react-native';
import { router } from 'expo-router';

import Onboarding from '@/app/(onboarding)/eye-calibration';
import { parseStatus } from '@/pi/parse';
import { speak } from '@/services/alerts';
import { pi } from '@/services/pi';
import { INITIAL_LIVE, useLive } from '@/state/live';

import { PiCalibrationScreen } from './index';
import { CLOSED_MS, OPEN_MS } from './machine';
import { usePiCalibration } from './use-pi-calibration';

jest.mock('expo-router', () => ({ router: { push: jest.fn(), back: jest.fn() } }));
jest.mock('@/services/alerts', () => ({ speak: jest.fn() }));
jest.mock('@/services/pi', () => ({ pi: () => ({ send: mockSend, streamUrl: () => null }) }));
jest.mock('@/components/live-view', () => ({ LiveView: () => null }));
jest.mock('@/components/progress-bar', () => ({ ProgressBar: () => null }));
jest.mock('expo-symbols', () => ({ SymbolView: () => null }));
jest.mock('expo-sqlite/kv-store', () => ({ Storage: { getItemSync: () => null, setItemSync: jest.fn() } }));
const mockSend = jest.fn().mockResolvedValue(undefined);

async function status(calibration: unknown, message = '') {
  await act(async () => useLive.setState({ status: parseStatus({ fps: 1, face: true, drowsiness: { calibration, message } }) }));
}
async function advance(ms: number) {
  await act(async () => jest.advanceTimersByTime(ms));
}
beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  mockSend.mockResolvedValue(undefined);
  useLive.setState({ ...INITIAL_LIVE, connection: 'online' });
});
afterEach(() => jest.useRealTimers());

test('ignores cached ok, observes calibrating after Start, latches ok and speaks once', async () => {
  await status('ok');
  const { result } = await renderHook(usePiCalibration);
  await act(async () => result.current.start());
  expect(pi().send).toHaveBeenCalledWith('POST', '/calibrate');
  await status('ok');
  expect(result.current.phase).toBe('open');
  await status('calibrating');
  await status('ok');
  expect(result.current.phase).toBe('done');
  await status('lost');
  await advance(40_000);
  expect(result.current.phase).toBe('done');
  expect((speak as jest.Mock).mock.calls.filter(([key]) => key === 'cal.done')).toHaveLength(1);
});

test.each([['failed', ''], [null, 'calibration failed: no face'], [null, 'calibrated']])(
  'ignores a leftover %s / %s until the unit reports calibrating', async (calibration, message) => {
    const { result } = await renderHook(usePiCalibration);
    await act(async () => result.current.start());
    await status(calibration, message); // left over from the previous run
    expect(result.current.phase).toBe('open');
    await status(message ? null : 'calibrating', message ? 'calibrating' : ''); // HTTP: message path
    await status(calibration, message);
    expect(result.current.phase).toBe(message === 'calibrated' ? 'done' : 'failed');
  },
);

test('allows the full 25 seconds after closed eyes and retry resets transition history', async () => {
  const { result } = await renderHook(usePiCalibration);
  await act(async () => result.current.start());
  await status('calibrating');
  await advance(OPEN_MS);
  expect(result.current.phase).toBe('closed');
  expect(speak).toHaveBeenCalledWith('cal.step2');
  await advance(CLOSED_MS);
  expect(result.current.phase).toBe('waiting');
  await advance(24_999);
  expect(result.current.phase).toBe('waiting');
  await advance(1);
  expect(result.current.phase).toBe('failed');
  await act(async () => result.current.start());
  await status('ok');
  expect(result.current.phase).toBe('open');
});

test('send failure is retryable and duplicate taps only send once', async () => {
  mockSend.mockRejectedValueOnce(new Error('disconnected'));
  const { result } = await renderHook(usePiCalibration);
  await act(async () => { void result.current.start(); void result.current.start(); });
  expect(mockSend).toHaveBeenCalledTimes(1);
  expect(result.current.phase).toBe('failed');
});

test('onboarding uses the unit screen and Done continues to emergency contacts', async () => {
  expect(Onboarding().type).toBe(PiCalibrationScreen);
  const view = await render(<Onboarding />);
  await fireEvent.press(view.getByText('Start'));
  await status('calibrating');
  await status('ok');
  await fireEvent.press(view.getByText('Done'));
  expect(router.push).toHaveBeenCalledWith('/emergency-contacts');
});

test('onboarding can skip offline or after failure; default Done goes back', async () => {
  useLive.setState({ connection: 'offline' });
  const view = await render(<Onboarding />);
  await fireEvent.press(view.getByText('Skip for now'));
  expect(router.push).toHaveBeenCalledWith('/emergency-contacts');
  await act(async () => useLive.setState({ connection: 'online' }));
  expect(view.queryByText('Skip for now')).toBeNull();
  await fireEvent.press(view.getByText('Start'));
  await status('calibrating');
  await status('failed');
  expect(view.getByText('Skip for now')).toBeTruthy();
  await view.unmount();
  const regular = await render(<PiCalibrationScreen />);
  await fireEvent.press(regular.getByText('Start'));
  await status(null, 'calibrating');
  await status(null, 'calibrated');
  await fireEvent.press(regular.getByText('Done'));
  expect(router.back).toHaveBeenCalled();
});

jest.mock('react-native-reanimated', () => ({
  __esModule: true,
  default: { View: jest.requireActual('react-native').View },
  useReducedMotion: () => true,
  cubicBezier: () => () => 0,
}));
