import { act, fireEvent, render, renderHook } from '@testing-library/react-native';
import { router } from 'expo-router';

import Onboarding from '@/app/(onboarding)/eye-calibration';
import { parseStatus } from '@/pi/parse';
import { speak } from '@/services/alerts';
import { pi } from '@/services/pi';
import { INITIAL_LIVE, useLive } from '@/state/live';

import { PiCalibrationScreen } from './index';
import { usePiCalibration } from './use-pi-calibration';

jest.mock('expo-router', () => ({ router: { push: jest.fn(), back: jest.fn() } }));
jest.mock('@/services/alerts', () => ({ speak: jest.fn() }));
jest.mock('@/services/pi', () => ({ pi: () => ({ send: mockSend, streamUrl: () => null }) }));
jest.mock('@/components/live-view', () => ({ LiveView: () => null }));
jest.mock('expo-symbols', () => ({ SymbolView: () => null }));
jest.mock('expo-sqlite/kv-store', () => ({ Storage: { getItemSync: () => null, setItemSync: jest.fn() } }));
const mockSend = jest.fn().mockResolvedValue(undefined);

async function status(calibration: unknown, message = '', calibration_step?: string, calibration_left_s?: number) {
  await act(async () => useLive.setState({ status: parseStatus({ fps: 1, face: true, drowsiness: { calibration, message, calibration_step, calibration_left_s } }) }));
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
  expect(result.current.phase).toBe('starting');
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
    expect(result.current.phase).toBe('starting');
    await status(message ? null : 'calibrating', message ? 'calibrating' : ''); // HTTP: message path
    await status(calibration, message);
    expect(result.current.phase).toBe(message === 'calibrated' ? 'done' : 'failed');
  },
);

test('no response fails at 15 seconds and retry ignores previous results', async () => {
  const { result } = await renderHook(usePiCalibration);
  await act(async () => result.current.start());
  await status('ok');
  await advance(14_999);
  expect(result.current.phase).toBe('starting');
  await advance(1);
  expect(result.current.phase).toBe('failed');
  expect(speak).toHaveBeenCalledWith('cal.failed');
  await act(async () => result.current.start());
  await status('ok');
  expect(result.current.phase).toBe('starting');
});

test('cap is 120 seconds from Start, regardless of step changes', async () => {
  const { result } = await renderHook(usePiCalibration);
  await act(async () => result.current.start());
  await advance(10_000);
  await status('calibrating', '', 'waiting_face');
  await advance(60_000);
  await status('calibrating', '', 'countdown_open', 3);
  await advance(49_999);
  expect(result.current.phase).toBe('following');
  await advance(1);
  expect(result.current.phase).toBe('failed');
  await status('ok');
  expect(result.current.phase).toBe('failed');
});

test('a step acknowledges Start but does not unlock leftover results', async () => {
  const { result } = await renderHook(usePiCalibration);
  await act(async () => result.current.start());
  await status(null, '', 'waiting_face');
  await advance(15_000);
  await status('ok');
  expect(result.current.phase).toBe('following');
  await status('calibrating');
  await status('ok');
  expect(result.current.phase).toBe('done');
});

test('unit steps drive text and speech once per entry, with no local countdown', async () => {
  const view = await render(<PiCalibrationScreen />);
  await fireEvent.press(view.getByText('Start'));
  expect(view.getByText('Waiting for your Sahi unit…')).toBeTruthy();
  const steps = [
    ['waiting_face', "We can't see your face. Look toward the camera.", 'cal.waitingFace'],
    ['countdown_open', 'Look ahead with your eyes open', 'cal.step1'],
    ['open', 'Look ahead with your eyes open', null], // already spoken at the countdown
    ['countdown_closed', 'Close your eyes', 'cal.step2'],
    ['closed', 'Keep your eyes closed', null],
  ] as const;
  for (const [step, text, speech] of steps) {
    jest.mocked(speak).mockClear();
    await status('calibrating', '', step, 2.2);
    expect(view.getByText(text)).toBeTruthy();
    expect(view.getByText('3 s')).toBeTruthy();
    await advance(5_000);
    expect(view.getByText('3 s')).toBeTruthy();
    await status('calibrating', '', step, 1);
    expect(view.getByText('1 s')).toBeTruthy();
    expect(speak).toHaveBeenCalledTimes(speech ? 1 : 0);
    if (speech) expect(speak).toHaveBeenCalledWith(speech);
  }
  await status('ok');
  expect(view.getByText('Calibration complete. You can open your eyes.')).toBeTruthy();
  expect(view.queryByText('1 s')).toBeNull();
});

test('a late send rejection from an expired attempt cannot fail a retry', async () => {
  let reject!: (reason: Error) => void;
  mockSend.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }));
  const { result } = await renderHook(usePiCalibration);
  await act(async () => { void result.current.start(); });
  await advance(15_000);
  await act(async () => result.current.start());
  await act(async () => reject(new Error('late failure')));
  expect(result.current.phase).toBe('starting');
  await status('calibrating');
  await status('ok');
  expect(result.current.phase).toBe('done');
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

test('onboarding can always skip until done; default Done goes back', async () => {
  useLive.setState({ connection: 'offline' });
  const view = await render(<Onboarding />);
  await fireEvent.press(view.getByText('Skip for now'));
  expect(router.push).toHaveBeenCalledWith('/emergency-contacts');
  await act(async () => useLive.setState({ connection: 'online' }));
  expect(view.getByText('Skip for now')).toBeTruthy(); // online too: calibration is optional
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
