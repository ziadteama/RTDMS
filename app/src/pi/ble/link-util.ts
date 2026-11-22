/**
 * Pure helpers for PlxBleLink: exponential backoff calculation, target matching,
 * and characteristic 06 result routing.
 */

import type { BleManager } from 'react-native-ble-plx';

import { CHAR_UUID } from './uuids';

export const defaultManagerFactory = (): BleManager => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { BleManager: PlxManager } = require('react-native-ble-plx');
  return new PlxManager() as BleManager;
};

export const MONITORED_CHARS = [
  ['ALERT', CHAR_UUID.ALERT],
  ['STATUS', CHAR_UUID.STATUS],
  ['PHYSIO', CHAR_UUID.PHYSIO],
  ['RESULT', CHAR_UUID.RESULT],
] as const;

/**
 * Computes reconnect exponential backoff:
 * 1s, 2s, 4s, 8s, capped at 15s, with ±20% jitter.
 */
export function computeBackoff(attempt: number, randomFn: () => number = Math.random): number {
  const baseMs = Math.min(1000 * Math.pow(2, Math.max(0, attempt)), 15000);
  const jitter = (randomFn() * 2 - 1) * 0.2; // -0.2 to +0.2
  return Math.round(baseMs * (1 + jitter));
}

/**
 * Checks whether an advertised device matches the target BLE name.
 */
export function matchesTarget(
  device: { name?: string | null; localName?: string | null },
  target: { name: string },
): boolean {
  if (!target?.name) return false;
  return device.name === target.name || device.localName === target.name;
}

/** Pi AuthGate rejects writes with ATT insufficient authentication. */
export function isAuthError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const e = error as { errorCode?: unknown; attErrorCode?: unknown };
  // ATT codes are distinct from ble-plx's generic CharacteristicWriteFailed (401).
  return [5, 8, 14].includes(Number(e.attErrorCode ?? e.errorCode));
}

type Pending = {
  resolve: (val: unknown) => void;
  reject: (err: unknown) => void;
  timer: ReturnType<typeof setTimeout>;
  hold: boolean;
};

/** Characteristic 06 has no reliable discriminator: all requests share one slot. */
export class ResultRouter {
  private pending: Pending | null = null;

  private register(kind: string, timeoutMs: number, hold = false): Promise<unknown> {
    if (this.pending) throw new Error('busy');
    const promise = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        const p = this.pending;
        if (!hold) this.pending = null;
        p?.reject(new Error(`BLE ${kind} timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending = { resolve, reject, timer, hold };
    });
    // A result can reject while the native write is still unresolved.
    void promise.catch(() => {});
    return promise;
  }

  registerCommand(timeoutMs: number): Promise<unknown> {
    return this.register('command', timeoutMs);
  }

  registerIncident(timeoutMs: number): Promise<unknown> {
    return this.register('incident', timeoutMs);
  }

  async request(kind: string, timeoutMs: number, write: () => Promise<unknown>): Promise<unknown> {
    const result = this.register(kind, timeoutMs, true);
    const registration = this.pending;
    let writeSettled = false;
    let finished = false;
    const release = () => {
      if (finished && writeSettled && this.pending === registration) this.pending = null;
    };
    try {
      let nativeWrite: Promise<unknown>;
      try { nativeWrite = write(); } catch (error) { writeSettled = true; throw error; }
      const writing = nativeWrite.finally(() => { writeSettled = true; release(); });
      const [, value] = await Promise.all([writing, result]);
      return value;
    } catch (error) {
      registration?.reject(error);
      throw error;
    } finally {
      finished = true;
      if (registration) clearTimeout(registration.timer);
      release();
    }
  }

  routeResult(value: unknown): boolean {
    const p = this.pending;
    if (!p) return false;
    if (!p.hold) this.pending = null;
    clearTimeout(p.timer);
    p.resolve(value);
    return true;
  }

  rejectAll(error: Error): void {
    const p = this.pending;
    this.pending = null;
    if (p) {
      clearTimeout(p.timer);
      p.reject(error);
    }
  }

  hasPending(): boolean { return this.pending !== null; }
}
