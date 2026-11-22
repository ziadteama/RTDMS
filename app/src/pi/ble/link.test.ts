import type { BleManager, State } from 'react-native-ble-plx';

import { decode } from './codec';
import { PlxBleLink } from './link';
import { FakeDevice, MockBleManager } from './link-test-support';
import type { BleNotify, BleTarget } from './types';
import { CHAR_UUID } from './uuids';

describe('PlxBleLink', () => {
  let fakeDevice: FakeDevice;
  let mockManager: MockBleManager;
  let link: PlxBleLink;
  const target: BleTarget = {
    name: 'RTDMS-Pi',
    token: 'k3Jx9mQ2pL7vN4wR8tY1',
  };

  beforeEach(() => {
    jest.useFakeTimers();
    fakeDevice = new FakeDevice();
    mockManager = new MockBleManager(fakeDevice);
    link = new PlxBleLink(() => mockManager as unknown as BleManager);
  });

  afterEach(() => {
    link.stop();
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  async function flushAsync(steps = 10): Promise<void> {
    for (let i = 0; i < steps; i++) {
      jest.advanceTimersByTime(10);
      await Promise.resolve();
    }
  }

  it('performs auth-first then clock write order upon connection and enters online', async () => {
    link.start(target);
    await flushAsync();

    expect(link.state).toBe('online');
    expect(link.deviceId).toBe('dev-test-1');

    // Verify write order: 1st auth, 2nd clock
    expect(fakeDevice.writes.length).toBe(2);
    expect(fakeDevice.writes[0]!.charUuid).toBe(CHAR_UUID.AUTH);
    const decodedAuth = decode(fakeDevice.writes[0]!.value) as { token: string };
    expect(decodedAuth.token).toBe(target.token);

    expect(fakeDevice.writes[1]!.charUuid).toBe(CHAR_UUID.CLOCK);
    const decodedClock = decode(fakeDevice.writes[1]!.value) as { phone_ms: number };
    expect(typeof decodedClock.phone_ms).toBe('number');

    // Verify all 4 characteristics subscribed: ALERT, STATUS, PHYSIO, RESULT
    expect(fakeDevice.monitors.has(CHAR_UUID.ALERT)).toBe(true);
    expect(fakeDevice.monitors.has(CHAR_UUID.STATUS)).toBe(true);
    expect(fakeDevice.monitors.has(CHAR_UUID.PHYSIO)).toBe(true);
    expect(fakeDevice.monitors.has(CHAR_UUID.RESULT)).toBe(true);
  });

  it('emits decoded notify values for alert, status, and physio', async () => {
    link.start(target);
    await flushAsync();

    const notifies: BleNotify[] = [];
    link.onNotify((n) => notifies.push(n));

    fakeDevice.emitMonitor(CHAR_UUID.ALERT, { pattern: 'short_beep', reasons: ['test'], t: 123 });
    fakeDevice.emitMonitor(CHAR_UUID.STATUS, { fps: 15, face: true, state: 'alert' });
    fakeDevice.emitMonitor(CHAR_UUID.PHYSIO, { hr_bpm: 72, watch_connected: true, t: 123 });

    expect(notifies.length).toBe(3);
    expect(notifies[0]!.kind).toBe('alert');
    expect((notifies[0]!.value as { pattern: string }).pattern).toBe('short_beep');
    expect(notifies[1]!.kind).toBe('status');
    expect(notifies[2]!.kind).toBe('physio');
    expect(link.lastNotifyAt).not.toBeNull();
  });

  it('resolves command via characteristic 06 result notification', async () => {
    link.start(target);
    await flushAsync();

    const cmdPromise = link.command({ cmd: 'test_alert', pattern: 'max' });
    expect(fakeDevice.writes.some((w) => w.charUuid === CHAR_UUID.COMMAND)).toBe(true);

    fakeDevice.emitMonitor(CHAR_UUID.RESULT, { ok: true, id: 'c1' });
    await expect(cmdPromise).resolves.toEqual({ ok: true, id: 'c1' });
  });

  it('rejects command on timeout', async () => {
    link.start(target);
    await flushAsync();

    const cmdPromise = link.command({ cmd: 'test_alert' }, 2000);
    jest.advanceTimersByTime(2000);

    await expect(cmdPromise).rejects.toThrow(/timed out/);
  });

  it('rejects pending command on link loss and reconnects with backoff schedule', async () => {
    link.start(target);
    await flushAsync();
    expect(link.state).toBe('online');

    const cmdPromise = link.command({ cmd: 'test_alert' });

    // Simulate device disconnect
    fakeDevice.simulateDisconnect();
    expect(link.state).toBe('offline');
    await expect(cmdPromise).rejects.toThrow('BLE link lost');

    // Fast forward reconnect timer (around 1000ms with jitter)
    jest.advanceTimersByTime(1500);
    await Promise.resolve();
    expect(link.state === 'connecting' || link.state === 'scanning' || link.state === 'online').toBe(true);
  });

  it('sets lastError=auth and does not hammer on auth rejection', async () => {
    // Make auth write fail
    const origWrite = fakeDevice.writeCharacteristicWithResponseForService.bind(fakeDevice);
    fakeDevice.writeCharacteristicWithResponseForService = async (s, charUuid, val) => {
      if (charUuid === CHAR_UUID.AUTH) {
        throw { errorCode: 401, attErrorCode: 5 };
      }
      return origWrite(s, charUuid, val);
    };

    link.start(target);
    await flushAsync();

    expect(link.state).toBe('offline');
    expect(link.lastError).toBe('auth');
    // Slow retry permits recovery after re-pairing.
    expect(jest.getTimerCount()).toBe(1);
  });

  it('reads settings and health characteristics', async () => {
    link.start(target);
    await flushAsync();

    const settings = await link.read('settings');
    expect(settings).toEqual({ profile: 'default' });

    const health = await link.read('health');
    expect(health).toEqual({ cpu_pct: 15, camera: 'ok' });

    await link.writeSettings({ sensitivity: 'high' });
    expect(fakeDevice.writes.some((w) => w.charUuid === CHAR_UUID.SETTINGS)).toBe(true);

    const rssi = await link.readRssi();
    expect(rssi).toBe(-60);
  });

  it('stop() cancels all activity and leaves exactly zero timers alive', async () => {
    link.start(target);
    await flushAsync();

    link.stop();

    expect(link.state).toBe('idle');
    expect(link.deviceId).toBe('dev-test-1');
    expect(mockManager.destroyed).toBe(true);
    expect(jest.getTimerCount()).toBe(0);
  });

  it('waits for Bluetooth to be PoweredOn when initial state is off', async () => {
    mockManager.btState = 'PoweredOff' as State;

    link.start(target);
    await flushAsync(2);

    expect(link.state).toBe('offline');
    expect(mockManager.stateListener).not.toBeNull();

    // Turn Bluetooth on
    mockManager.btState = 'PoweredOn' as State;
    mockManager.stateListener!('PoweredOn' as State);

    await flushAsync();
    expect(link.state).toBe('online');
  });
});
