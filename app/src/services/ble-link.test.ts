import { setBleLinkForTest } from '@/pi/ble';
import { FakeBleLink } from '@/pi/ble/fake-link';
import { requestBlePermissions } from '@/pi/ble/permissions';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';

import { startBleLink } from './ble-link';

jest.mock('expo-sqlite/kv-store', () => ({
  Storage: { getItemSync: jest.fn(() => null), setItemSync: jest.fn(), removeItemSync: jest.fn(), clearSync: jest.fn() },
}));
jest.mock('expo-secure-store', () => ({
  getItem: jest.fn(() => null),
  setItem: jest.fn(),
  deleteItemAsync: jest.fn(async () => {}),
}));
jest.mock('@/pi/ble/permissions', () => ({ requestBlePermissions: jest.fn(async () => true) }));

const TOKEN = 'k3Jx9mQ2pL7vN4wR8tY1';
const flush = () => new Promise((r) => setImmediate(r));
let link: FakeBleLink;

beforeEach(() => {
  link = new FakeBleLink();
  setBleLinkForTest(link);
  useSettings.getState().reset();
  useSecure.getState().wipe();
  jest.mocked(requestBlePermissions).mockResolvedValue(true);
});
afterEach(() => setBleLinkForTest(null));

describe('startBleLink', () => {
  it('stays idle without a pairing, then starts when name and token appear', async () => {
    const stop = startBleLink();
    await flush();
    expect(link.state).toBe('idle');
    useSettings.getState().set({ bleName: 'RTDMS-Pi' });
    await flush();
    expect(link.state).toBe('idle'); // still no token
    useSecure.getState().setPiToken(TOKEN);
    await flush();
    expect(link.state).toBe('scanning');
    expect(link.target).toEqual({ name: 'RTDMS-Pi', token: TOKEN, deviceId: null });
    stop();
  });

  it('stops the link in demo mode and when the pairing is removed', async () => {
    useSettings.getState().set({ bleName: 'RTDMS-Pi' });
    useSecure.getState().setPiToken(TOKEN);
    const stop = startBleLink();
    await flush();
    expect(link.state).toBe('scanning');
    useSettings.getState().set({ demo: true });
    expect(link.state).toBe('idle');
    useSettings.getState().set({ demo: false });
    await flush();
    expect(link.state).toBe('scanning');
    useSettings.getState().set({ bleName: null });
    expect(link.state).toBe('idle');
    stop();
  });

  it('remembers the peripheral id once online, only when it changed', async () => {
    useSettings.getState().set({ bleName: 'RTDMS-Pi' });
    useSecure.getState().setPiToken(TOKEN);
    const stop = startBleLink();
    await flush();
    link.setState('online');
    expect(useSettings.getState().bleDeviceId).toBe('fake-device');
    const set = jest.spyOn(useSettings.getState(), 'set');
    link.setState('offline');
    link.setState('online');
    expect(set).not.toHaveBeenCalled();
    stop();
  });

  it('does not start when the Bluetooth permission is denied', async () => {
    jest.mocked(requestBlePermissions).mockResolvedValue(false);
    useSettings.getState().set({ bleName: 'RTDMS-Pi' });
    useSecure.getState().setPiToken(TOKEN);
    const stop = startBleLink();
    await flush();
    expect(link.state).toBe('idle');
    stop();
  });

  it('stops the link and unsubscribes on cleanup', async () => {
    useSettings.getState().set({ bleName: 'RTDMS-Pi' });
    useSecure.getState().setPiToken(TOKEN);
    const stop = startBleLink();
    await flush();
    stop();
    expect(link.state).toBe('idle');
    useSettings.getState().set({ bleName: 'Other' });
    await flush();
    expect(link.state).toBe('idle');
  });
});
