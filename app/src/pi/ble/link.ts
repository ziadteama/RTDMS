/**
 * Concrete BleLink implementation backed by react-native-ble-plx.
 * Lazy initialization on first start(), clean teardown on stop().
 */

import type { BleManager, Device, Subscription } from 'react-native-ble-plx';

import { authPayload, clockPayload, decode, encode } from './codec';
import { computeBackoff, defaultManagerFactory, matchesTarget, MONITORED_CHARS, ResultRouter } from './link-util';
import type { BleLink, BleNotify, BleState, BleTarget } from './types';
import { CHAR_UUID, SERVICE_UUID } from './uuids';

export class PlxBleLink implements BleLink {
  state: BleState = 'idle';
  lastNotifyAt: number | null = null;
  deviceId: string | null = null;
  lastError: string | null = null;

  private target: BleTarget | null = null;
  private manager: BleManager | null = null;
  private connectedDevice: Device | null = null;
  private stateCbs = new Set<(s: BleState) => void>();
  private notifyCbs = new Set<(n: BleNotify) => void>();
  private subscriptions: Subscription[] = [];
  private router = new ResultRouter();

  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private scanTimer: ReturnType<typeof setTimeout> | null = null;
  private onlineSince: number | null = null;
  private connectingInProgress = false;
  private btStateSub: Subscription | null = null;

  constructor(private readonly managerFactory: () => BleManager = defaultManagerFactory) {}

  start(target: BleTarget): void {
    const cur = this.target;
    if (this.state !== 'idle' && cur && cur.name === target.name && cur.token === target.token && cur.deviceId === target.deviceId) {
      return;
    }
    this.cleanupConnection();
    this.target = target;
    this.lastError = null;
    this.reconnectAttempt = 0;
    this.setState('connecting');
    this.manager ??= this.managerFactory();
    void this.checkStateAndConnect();
  }

  stop(): void {
    this.cleanupConnection();
    this.target = null;
    this.lastError = null;
    this.reconnectAttempt = 0;
    if (this.manager) {
      void this.manager.destroy().catch(() => {});
      this.manager = null;
    }
    this.setState('idle');
  }

  onState(cb: (state: BleState) => void): () => void {
    this.stateCbs.add(cb);
    return () => void this.stateCbs.delete(cb);
  }

  onNotify(cb: (n: BleNotify) => void): () => void {
    this.notifyCbs.add(cb);
    return () => void this.notifyCbs.delete(cb);
  }

  private setState(next: BleState): void {
    if (this.state === next) return;
    this.state = next;
    this.stateCbs.forEach((cb) => cb(next));
  }

  private async checkStateAndConnect(): Promise<void> {
    if (!this.manager || !this.target) return;
    try {
      const btState = await this.manager.state();
      if (btState !== 'PoweredOn') {
        this.setState('offline');
        this.btStateSub?.remove();
        this.btStateSub = this.manager.onStateChange((s) => {
          if (s === 'PoweredOn') {
            this.btStateSub?.remove();
            this.btStateSub = null;
            void this.connectOrScan();
          }
        }, false);
        return;
      }
      await this.connectOrScan();
    } catch {
      this.setState('offline');
      this.scheduleReconnect();
    }
  }

  private async connectOrScan(): Promise<void> {
    if (this.connectingInProgress || !this.target || !this.manager) return;
    this.connectingInProgress = true;
    try {
      if (this.target.deviceId) {
        this.setState('connecting');
        try {
          const dev = await this.manager.connectToDevice(this.target.deviceId);
          await this.setupDevice(dev);
          return;
        } catch {
          // Fast reconnect failed, fall through to scanning
        }
      }
      await this.startScan();
    } finally {
      this.connectingInProgress = false;
    }
  }

  private async startScan(): Promise<void> {
    if (!this.manager || !this.target) return;
    this.setState('scanning');
    this.scanTimer = setTimeout(() => {
      this.stopScan();
      this.setState('offline');
      this.scheduleReconnect();
    }, 15000);

    await this.manager.startDeviceScan([SERVICE_UUID], { scanMode: 1 }, async (err, dev) => {
      if (err || !dev || !this.target) {
        this.stopScan();
        this.setState('offline');
        this.scheduleReconnect();
        return;
      }
      if (matchesTarget(dev, this.target)) {
        this.stopScan();
        this.setState('connecting');
        try {
          const connected = await dev.connect();
          await this.setupDevice(connected);
        } catch {
          this.setState('offline');
          this.scheduleReconnect();
        }
      }
    });
  }

  private stopScan(): void {
    if (this.scanTimer) {
      clearTimeout(this.scanTimer);
      this.scanTimer = null;
    }
    this.manager?.stopDeviceScan().catch(() => {});
  }

  private async setupDevice(device: Device): Promise<void> {
    device.onDisconnected(() => this.handleDisconnected());
    try {
      await device.requestMTU(247);
    } catch {
      // Default MTU still works
    }
    await device.discoverAllServicesAndCharacteristics();

    // 1st write: auth; on rejection set lastError='auth' and do not hammer
    try {
      const authB64 = encode(authPayload(this.target!.token));
      await device.writeCharacteristicWithResponseForService(SERVICE_UUID, CHAR_UUID.AUTH, authB64);
    } catch {
      this.lastError = 'auth';
      this.setState('offline');
      void device.cancelConnection().catch(() => {});
      return;
    }

    // 2nd write: clock
    const clockB64 = encode(clockPayload(Date.now()));
    await device.writeCharacteristicWithResponseForService(SERVICE_UUID, CHAR_UUID.CLOCK, clockB64);

    this.subscribeAll(device);
    this.connectedDevice = device;
    this.deviceId = device.id;
    this.onlineSince = Date.now();
    this.lastError = null;
    this.setState('online');
  }

  private subscribeAll(device: Device): void {
    for (const [key, uuid] of MONITORED_CHARS) {
      const sub = device.monitorCharacteristicForService(SERVICE_UUID, uuid, (_err, char) => {
        if (!char?.value) return;
        const val = decode(char.value);
        if (val === null) return;
        if (key === 'RESULT') {
          this.router.routeResult(val);
        } else {
          this.lastNotifyAt = Date.now();
          const kind = key.toLowerCase() as 'alert' | 'status' | 'physio';
          this.notifyCbs.forEach((cb) => cb({ kind, value: val, at: this.lastNotifyAt! }));
        }
      });
      this.subscriptions.push(sub);
    }
  }

  private handleDisconnected(): void {
    this.subscriptions.forEach((s) => s.remove());
    this.subscriptions = [];
    if (this.onlineSince !== null && Date.now() - this.onlineSince >= 10000) {
      this.reconnectAttempt = 0;
    }
    this.onlineSince = null;
    this.connectedDevice = null;
    this.router.rejectAll(new Error('BLE link lost'));
    if (this.state !== 'idle') {
      this.setState('offline');
      if (this.lastError !== 'auth' && this.target) this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer || this.state === 'idle' || !this.target || this.lastError === 'auth') return;
    const delay = computeBackoff(this.reconnectAttempt++);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.connectOrScan();
    }, delay);
  }

  private cleanupConnection(): void {
    this.stopScan();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.btStateSub?.remove();
    this.btStateSub = null;
    this.subscriptions.forEach((s) => s.remove());
    this.subscriptions = [];
    this.router.rejectAll(new Error('BLE stopped'));
    if (this.connectedDevice) {
      void this.connectedDevice.cancelConnection().catch(() => {});
      this.connectedDevice = null;
    }
    this.onlineSince = null;
  }

  private needDevice(): Device {
    if (this.state !== 'online' || !this.connectedDevice) throw new Error('BLE: not online');
    return this.connectedDevice;
  }

  async read(char: 'settings' | 'health'): Promise<unknown> {
    const dev = this.needDevice();
    const uuid = char === 'settings' ? CHAR_UUID.SETTINGS : CHAR_UUID.HEALTH;
    const c = await dev.readCharacteristicForService(SERVICE_UUID, uuid);
    const val = decode(c.value);
    if (val === null) throw new Error(`BLE: failed to decode ${char}`);
    return val;
  }

  async writeSettings(body: unknown): Promise<void> {
    const dev = this.needDevice();
    await dev.writeCharacteristicWithResponseForService(SERVICE_UUID, CHAR_UUID.SETTINGS, encode(body));
  }

  async command(body: unknown, timeoutMs = 4000): Promise<unknown> {
    const dev = this.needDevice();
    const p = this.router.registerCommand(timeoutMs);
    await dev.writeCharacteristicWithResponseForService(SERVICE_UUID, CHAR_UUID.COMMAND, encode(body));
    return p;
  }

  async incident(body: unknown, timeoutMs = 6000): Promise<unknown> {
    const dev = this.needDevice();
    const p = this.router.registerIncident(timeoutMs);
    await dev.writeCharacteristicWithResponseForService(SERVICE_UUID, CHAR_UUID.INCIDENT, encode(body));
    return p;
  }

  async readRssi(): Promise<number | null> {
    if (this.state !== 'online' || !this.connectedDevice) return null;
    const dev = await this.connectedDevice.readRSSI();
    return dev.rssi ?? null;
  }
}
