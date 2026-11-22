import type { BleManager, State, Subscription } from 'react-native-ble-plx';

import { decode, encode } from './codec';
import { PlxBleLink } from './link';
import type { BleNotify, BleTarget } from './types';
import { CHAR_UUID } from './uuids';

class FakeDevice {
  id = 'dev-test-1';
  name: string | null = 'RTDMS-Pi';
  localName: string | null = null;
  rssi: number | null = -60;

  writes: { charUuid: string; value: string }[] = [];
  monitors = new Map<string, (err: unknown, char: { value: string } | null) => void>();
  disconnectCb: ((err: unknown, dev: FakeDevice) => void) | null = null;
  connected = true;

  async connect(): Promise<FakeDevice> {
    this.connected = true;
    return this;
  }

  async cancelConnection(): Promise<FakeDevice> {
    this.connected = false;
    return this;
  }

  onDisconnected(cb: (err: unknown, dev: FakeDevice) => void): Subscription {
    this.disconnectCb = cb;
    return { remove: () => (this.disconnectCb = null) } as Subscription;
  }

  async requestMTU(_mtu: number): Promise<FakeDevice> {
    return this;
  }

  async discoverAllServicesAndCharacteristics(): Promise<FakeDevice> {
    return this;
  }

  async readRSSI(): Promise<FakeDevice> {
    return this;
  }

  async readCharacteristicForService(_s: string, charUuid: string): Promise<{ value: string }> {
    if (charUuid === CHAR_UUID.SETTINGS) {
      return { value: encode({ profile: 'default' }) };
    }
    if (charUuid === CHAR_UUID.HEALTH) {
      return { value: encode({ cpu_pct: 15, camera: 'ok' }) };
    }
    throw new Error('unknown char');
  }

  async writeCharacteristicWithResponseForService(_s: string, charUuid: string, value: string): Promise<void> {
    this.writes.push({ charUuid, value });
  }

  monitorCharacteristicForService(
    _s: string,
    charUuid: string,
    cb: (err: unknown, char: { value: string } | null) => void,
  ): Subscription {
    this.monitors.set(charUuid, cb);
    return {
      remove: () => {
        this.monitors.delete(charUuid);
      },
    } as Subscription;
  }

  emitMonitor(charUuid: string, payload: unknown): void {
    const cb = this.monitors.get(charUuid);
    if (cb) {
      cb(null, { value: encode(payload) });
    }
  }

  simulateDisconnect(): void {
    this.connected = false;
    if (this.disconnectCb) {
      this.disconnectCb(new Error('connection terminated'), this);
    }
  }
}

class MockBleManager {
  btState: State = 'PoweredOn' as State;
  stateListener: ((s: State) => void) | null = null;
  devices = new Map<string, FakeDevice>();
  scanListener: ((err: unknown, dev: FakeDevice | null) => void) | null = null;
  isScanning = false;
  destroyed = false;

  constructor(public currentDevice: FakeDevice = new FakeDevice()) {
    this.devices.set(currentDevice.id, currentDevice);
  }

  async state(): Promise<State> {
    return this.btState;
  }

  onStateChange(cb: (s: State) => void): Subscription {
    this.stateListener = cb;
    return {
      remove: () => {
        this.stateListener = null;
      },
    } as Subscription;
  }

  async startDeviceScan(
    _uuids: unknown,
    _opts: unknown,
    cb: (err: unknown, dev: FakeDevice | null) => void,
  ): Promise<void> {
    this.isScanning = true;
    this.scanListener = cb;
    // Emit device immediately if available
    if (this.currentDevice) {
      setTimeout(() => {
        if (this.isScanning && this.scanListener) {
          this.scanListener(null, this.currentDevice);
        }
      }, 10);
    }
  }

  async stopDeviceScan(): Promise<void> {
    this.isScanning = false;
    this.scanListener = null;
  }

  async connectToDevice(id: string): Promise<FakeDevice> {
    const dev = this.devices.get(id);
    if (!dev) throw new Error('Device not found');
    await dev.connect();
    return dev;
  }

  async destroy(): Promise<void> {
    this.destroyed = true;
  }
}

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
        throw new Error('GATT write rejected: auth failed');
      }
      return origWrite(s, charUuid, val);
    };

    link.start(target);
    await flushAsync();

    expect(link.state).toBe('offline');
    expect(link.lastError).toBe('auth');
    // Ensure no reconnect timer scheduled
    expect(jest.getTimerCount()).toBe(0);
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
