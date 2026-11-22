import type { State, Subscription } from 'react-native-ble-plx';
import { encode } from './codec';
import { CHAR_UUID } from './uuids';

export class FakeDevice {
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

export class MockBleManager {
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

  async cancelDeviceConnection(id: string): Promise<FakeDevice | undefined> {
    return this.devices.get(id)?.cancelConnection();
  }

  async destroy(): Promise<void> {
    this.destroyed = true;
  }
}

