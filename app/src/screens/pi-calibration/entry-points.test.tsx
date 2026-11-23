import { act, fireEvent, render } from '@testing-library/react-native';
import { router } from 'expo-router';

import { parseStatus } from '@/pi/parse';
import { Diagnostics } from '@/screens/diagnostics';
import { UnitSection } from '@/screens/settings/unit-section';
import { INITIAL_LIVE, useLive } from '@/state/live';

jest.mock('expo-router', () => ({ router: { push: jest.fn() } }));
jest.mock('expo-symbols', () => ({ SymbolView: () => null }));
jest.mock('expo-sqlite/kv-store', () => ({ Storage: { getItemSync: () => null, setItemSync: jest.fn() } }));
jest.mock('@/state/secure', () => ({ useSecure: { getState: () => ({ setWifi: jest.fn() }) } }));
jest.mock('@/screens/diagnostics/connection', () => ({ ConnectionDiag: () => null }));
jest.mock('@/screens/diagnostics/detection-tuning', () => ({ DetectionTuning: () => null }));
jest.mock('@/screens/diagnostics/raw-metrics', () => ({ RawMetrics: () => null }));
jest.mock('@/screens/diagnostics/unit-health', () => ({ UnitHealth: () => null }));

beforeEach(() => {
  jest.clearAllMocks();
  useLive.setState({ ...INITIAL_LIVE, connection: 'online' });
});

test.each([
  ['ok', false, 'Done'], ['calibrating', true, 'In progress'], ['failed', true, 'Not done'],
  ['lost', true, 'Not done'], [null, true, 'Done'], [null, false, 'Not done'],
])('Settings uses unit state %s and links to /calibrate', async (calibration, calibrated, label) => {
  useLive.setState({ status: parseStatus({ fps: 1, face: true, drowsiness: { calibration, calibrated } }) });
  const view = await render(<UnitSection />);
  expect(view.getByText(label as string)).toBeTruthy();
  expect(view.queryByText('Eye calibration')).toBeNull();
  expect(view.queryByText('Driving position')).toBeNull();
  await fireEvent.press(view.getByText('Calibrate'));
  expect(router.push).toHaveBeenCalledWith('/calibrate');
  jest.clearAllMocks();
  await act(async () => useLive.setState({ connection: 'offline' }));
  await fireEvent.press(view.getByText('Calibrate'));
  expect(router.push).not.toHaveBeenCalled();
});

test('Diagnostics links to the preserved legacy phone flow', async () => {
  const view = await render(<Diagnostics />);
  await fireEvent.press(view.getByText('Phone-camera eye calibration (legacy)'));
  expect(router.push).toHaveBeenCalledWith('/eye-calibration');
});

jest.mock('react-native-reanimated', () => ({
  __esModule: true,
  default: { View: jest.requireActual('react-native').View },
  useReducedMotion: () => true,
  cubicBezier: () => () => 0,
}));
