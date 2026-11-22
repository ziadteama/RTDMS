/** Session-scoped BLE connection and notifications, with one shared result slot. */
import type { BleManager, Device, Subscription } from 'react-native-ble-plx';

import { authPayload, clockPayload, decode, encode } from './codec';
import { computeBackoff, defaultManagerFactory, isAuthError, matchesTarget, MONITORED_CHARS, ResultRouter } from './link-util';
import type { BleLink, BleNotify, BleState, BleTarget, BleUnit } from './types';
import { CHAR_UUID, SERVICE_UUID } from './uuids';

export class PlxBleLink implements BleLink {
  state: BleState = 'idle';
  lastNotifyAt: number | null = null;
  deviceId: string | null = null;
  lastError: string | null = null;
  /** True while the phone's Bluetooth radio is off or unusable (the link waits for it to come back). */
  btOff = false;
  private session = 0;
  private target: BleTarget | null = null;
  private manager: BleManager | null = null;
  private connectedDevice: Device | null = null;
  private connectingId: string | null = null;
  private disconnectSub: Subscription | null = null;
  private stateCbs = new Set<(s: BleState) => void>();
  private notifyCbs = new Set<(n: BleNotify) => void>();
  private subscriptions: Subscription[] = [];
  private router = new ResultRouter();
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private scanTimer: ReturnType<typeof setTimeout> | null = null;
  private onlineSince: number | null = null;
  private btStateSub: Subscription | null = null;

  constructor(private readonly managerFactory: () => BleManager = defaultManagerFactory) {}

  start(target: BleTarget): void {
    const cur = this.target;
    if (this.state !== 'idle' && cur && cur.name === target.name && cur.token === target.token && cur.deviceId === target.deviceId) return;
    ++this.session;
    this.cleanupConnection();
    this.target = target;
    this.lastError = null;
    this.reconnectAttempt = 0;
    this.setState('connecting');
    this.manager ??= this.managerFactory();
    void this.checkStateAndConnect(this.session);
  }

  stop(): void {
    ++this.session;
    this.cleanupConnection();
    this.target = null;
    this.lastError = null;
    this.btOff = false;
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

  private current(session: number): boolean { return session === this.session && this.target !== null; }

  private setState(next: BleState): void {
    if (this.state === next) return;
    this.state = next;
    this.stateCbs.forEach((cb) => cb(next));
  }

  private async checkStateAndConnect(session: number): Promise<void> {
    const manager = this.manager;
    if (!manager || !this.current(session)) return;
    try {
      const btState = await manager.state();
      if (!this.current(session)) return;
      this.btOff = btState !== 'PoweredOn';
      if (btState !== 'PoweredOn') {
        this.setState('offline');
        this.btStateSub?.remove();
        this.btStateSub = manager.onStateChange((s) => {
          if (this.current(session) && s === 'PoweredOn') {
            this.btStateSub?.remove();
            this.btStateSub = null;
            this.btOff = false;
            void this.connectOrScan(session);
          }
        }, false);
        return;
      }
      await this.connectOrScan(session);
    } catch (error) { this.failed(session, error); }
  }

  private async connectOrScan(session: number): Promise<void> {
    const manager = this.manager;
    const target = this.target;
    if (!manager || !target || !this.current(session)) return;
    try {
      if (target.deviceId) {
        this.setState('connecting');
        this.connectingId = target.deviceId;
        let dev: Device;
        try { dev = await manager.connectToDevice(target.deviceId); }
        catch (error) {
          if (!this.current(session)) return;
          this.connectingId = null;
          if (isAuthError(error)) throw error;
          await this.startScan(session);
          return;
        }
        if (!this.current(session)) return;
        await this.setupDevice(dev, session);
      } else await this.startScan(session);
    } catch (error) { this.failed(session, error); }
  }

  private async startScan(session: number): Promise<void> {
    if (!this.manager || !this.current(session)) return;
    this.setState('scanning');
    this.scanTimer = setTimeout(() => this.failed(session, new Error('scan timeout')), 15000);
    let claimed = false;
    await this.manager.startDeviceScan([SERVICE_UUID], { scanMode: 1 }, (err, dev) => {
      if (!this.current(session) || claimed) return;
      if (err) { this.failed(session, err); return; }
      if (!dev || !this.target || !matchesTarget(dev, this.target)) return;
      claimed = true;
      this.stopScan();
      this.connectingId = dev.id;
      this.setState('connecting');
      void (async () => {
        try {
          const connected = await dev.connect();
          if (!this.current(session)) return;
          await this.setupDevice(connected, session);
        } catch (error) { this.failed(session, error); }
      })();
    });
  }

  private stopScan(): void {
    if (this.scanTimer) clearTimeout(this.scanTimer);
    this.scanTimer = null;
    void this.manager?.stopDeviceScan().catch(() => {});
  }

  private async setupDevice(device: Device, session: number): Promise<void> {
    this.disconnectSub = device.onDisconnected(() => {
      if (this.current(session)) this.handleDisconnected();
    });
    try { await device.requestMTU(247); } catch { /* Default MTU fallback. */ }
    if (!this.current(session)) return;
    await device.discoverAllServicesAndCharacteristics();
    if (!this.current(session)) return;
    // No token: the unit is in DEV open mode and takes writes without auth (a token-mode unit rejects the clock write below).
    if (this.target!.token) {
      await device.writeCharacteristicWithResponseForService(SERVICE_UUID, CHAR_UUID.AUTH, encode(authPayload(this.target!.token)));
      if (!this.current(session)) return;
    }
    await device.writeCharacteristicWithResponseForService(SERVICE_UUID, CHAR_UUID.CLOCK, encode(clockPayload(Date.now())));
    if (!this.current(session)) return;
    this.subscribeAll(device, session);
    this.connectedDevice = device;
    this.connectingId = null;
    this.deviceId = device.id;
    this.onlineSince = Date.now();
    this.lastError = null;
    this.setState('online');
  }

  private subscribeAll(device: Device, session: number): void {
    for (const [key, uuid] of MONITORED_CHARS) {
      this.subscriptions.push(device.monitorCharacteristicForService(SERVICE_UUID, uuid, (_err, char) => {
        if (!this.current(session) || !char?.value) return;
        const val = decode(char.value);
        if (val === null) return;
        if (key === 'RESULT') this.router.routeResult(val);
        else {
          this.lastNotifyAt = Date.now();
          const kind = key.toLowerCase() as 'alert' | 'status' | 'physio';
          this.notifyCbs.forEach((cb) => cb({ kind, value: val, at: this.lastNotifyAt! }));
        }
      }));
    }
  }

  private failed(session: number, error: unknown): void {
    if (!this.current(session)) return;
    this.lastError = isAuthError(error) ? 'auth' : 'connection';
    this.handleDisconnected();
  }

  private handleDisconnected(): void {
    ++this.session; // Invalidate pending setup and callbacks from this connection attempt.
    if (this.onlineSince !== null && Date.now() - this.onlineSince >= 10000) this.reconnectAttempt = 0;
    this.cleanupConnection();
    if (this.target) {
      this.setState('offline');
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer || !this.target) return;
    const session = this.session;
    const delay = this.lastError === 'auth' ? 15000 : computeBackoff(this.reconnectAttempt++);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.current(session)) void this.checkStateAndConnect(session);
    }, delay);
  }

  private cleanupConnection(): void {
    this.stopScan();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.btStateSub?.remove();
    this.btStateSub = null;
    this.disconnectSub?.remove();
    this.disconnectSub = null;
    this.subscriptions.forEach((s) => s.remove());
    this.subscriptions = [];
    this.router.rejectAll(new Error('BLE link lost or stopped'));
    if (this.connectingId) void this.manager?.cancelDeviceConnection(this.connectingId).catch(() => {});
    if (this.connectedDevice) void this.connectedDevice.cancelConnection().catch(() => {});
    this.connectingId = null;
    this.connectedDevice = null;
    this.onlineSince = null;
    this.lastNotifyAt = null;
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
    await this.needDevice().writeCharacteristicWithResponseForService(SERVICE_UUID, CHAR_UUID.SETTINGS, encode(body));
  }

  private async request(kind: 'command' | 'incident', body: unknown, timeoutMs: number): Promise<unknown> {
    const dev = this.needDevice();
    const encoded = encode(body);
    const uuid = kind === 'command' ? CHAR_UUID.COMMAND : CHAR_UUID.INCIDENT;
    return this.router.request(kind, timeoutMs, () => dev.writeCharacteristicWithResponseForService(SERVICE_UUID, uuid, encoded));
  }

  command(body: unknown, timeoutMs = 4000): Promise<unknown> { return this.request('command', body, timeoutMs); }
  incident(body: unknown, timeoutMs = 6000): Promise<unknown> { return this.request('incident', body, timeoutMs); }

  async scan(name: string, ms = 6000): Promise<BleUnit[]> {
    const manager = (this.manager ??= this.managerFactory());
    const found = new Map<string, BleUnit>();
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(done, ms);
      function done(err?: unknown) {
        clearTimeout(timer);
        void manager.stopDeviceScan().catch(() => {});
        if (err) reject(err);
        else resolve();
      }
      void manager
        .startDeviceScan([SERVICE_UUID], { scanMode: 1 }, (err, dev) => {
          if (err) return done(err);
          if (dev && matchesTarget(dev, { name })) found.set(dev.id, { id: dev.id, name: dev.name ?? dev.localName ?? name, rssi: dev.rssi ?? null });
        })
        .catch(done);
    });
    return [...found.values()].sort((a, b) => (b.rssi ?? -999) - (a.rssi ?? -999));
  }

  async readRssi(): Promise<number | null> {
    if (this.state !== 'online' || !this.connectedDevice) return null;
    const dev = await this.connectedDevice.readRSSI();
    return dev.rssi ?? null;
  }
}
