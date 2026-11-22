import type { BleLink, BleNotify, BleNotifyKind, BleState, BleTarget } from './types';

/**
 * In-memory BleLink for Jest, the web build and screenshots (same idea as FakeFaceSource). Tests
 * drive it with setState() / emit(); `handlers` answer reads and writes like a Pi would.
 */
export class FakeBleLink implements BleLink {
  state: BleState = 'idle';
  lastNotifyAt: number | null = null;
  deviceId: string | null = null;
  rssi: number | null = -55;
  target: BleTarget | null = null;
  /** Canned answers: read('health'), command(), incident(). Missing handler rejects. */
  handlers: {
    settings?: () => unknown;
    health?: () => unknown;
    command?: (body: unknown) => unknown;
    incident?: (body: unknown) => unknown;
  } = {};
  written: { char: 'settings' | 'command' | 'incident'; body: unknown }[] = [];
  private stateCbs = new Set<(s: BleState) => void>();
  private notifyCbs = new Set<(n: BleNotify) => void>();

  start(target: BleTarget) {
    this.target = target;
    this.setState('scanning');
  }
  stop() {
    this.target = null;
    this.setState('idle');
  }
  onState(cb: (s: BleState) => void) {
    this.stateCbs.add(cb);
    return () => void this.stateCbs.delete(cb);
  }
  onNotify(cb: (n: BleNotify) => void) {
    this.notifyCbs.add(cb);
    return () => void this.notifyCbs.delete(cb);
  }
  setState(s: BleState) {
    if (s === this.state) return;
    this.state = s;
    if (s === 'online') this.deviceId = this.target?.deviceId ?? 'fake-device';
    this.stateCbs.forEach((cb) => cb(s));
  }
  emit(kind: BleNotifyKind, value: unknown, at = Date.now()) {
    this.lastNotifyAt = at;
    this.notifyCbs.forEach((cb) => cb({ kind, value, at }));
  }
  private need<T>(h: (() => T) | undefined): Promise<T> {
    if (this.state !== 'online' || !h) return Promise.reject(new Error('ble: not online or no handler'));
    return Promise.resolve(h());
  }
  read(char: 'settings' | 'health') {
    return this.need(this.handlers[char]);
  }
  async writeSettings(body: unknown) {
    if (this.state !== 'online') throw new Error('ble: not online');
    this.written.push({ char: 'settings', body });
  }
  command(body: unknown) {
    this.written.push({ char: 'command', body });
    const h = this.handlers.command;
    return this.need(h && (() => h(body)));
  }
  incident(body: unknown) {
    this.written.push({ char: 'incident', body });
    const h = this.handlers.incident;
    return this.need(h && (() => h(body)));
  }
  async readRssi() {
    return this.state === 'online' ? this.rssi : null;
  }
}
