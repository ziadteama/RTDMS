import { act, fireEvent, render, screen } from '@testing-library/react-native';

import { UnitSection } from './unit-section';
import { useLive } from '@/state/live';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({ router: { push: (...a: unknown[]) => mockPush(...a) } }));
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: { getItemSync: () => null, setItemSync: jest.fn(), removeItemSync: jest.fn(), clearSync: jest.fn() },
}));
jest.mock('expo-symbols', () => ({ SymbolView: () => null }));

beforeEach(() => {
  mockPush.mockClear();
  useLive.setState({ connection: 'online', link: null });
});

it('opens pairing from "Connect a different unit"', async () => {
  await render(<UnitSection />);
  await fireEvent.press(screen.getByText('Connect a different unit'));
  expect(mockPush).toHaveBeenCalledWith('/pair');
});

it('shows the link kind on the status row when known', async () => {
  await act(async () => useLive.setState({ link: 'ble' }));
  const { rerender } = await render(<UnitSection />);
  expect(screen.getByText('Connected via Bluetooth')).toBeTruthy();
  await act(async () => useLive.setState({ link: 'http' }));
  await rerender(<UnitSection />);
  expect(screen.getByText('Connected via Wi-Fi')).toBeTruthy();
});
