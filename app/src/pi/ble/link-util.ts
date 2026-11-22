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

type Pending = {
  resolve: (val: unknown) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
};

/**
 * Routes characteristic 06 notifications to pending command / incident promises.
 * Only single request in flight per type; rejects concurrent calls with 'busy'.
 */
export class ResultRouter {
  private pendingCommand: Pending | null = null;
  private pendingIncident: Pending | null = null;

  registerCommand(timeoutMs: number): Promise<unknown> {
    if (this.pendingCommand) {
      return Promise.reject(new Error('busy'));
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingCommand = null;
        reject(new Error(`BLE command timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pendingCommand = { resolve, reject, timer };
    });
  }

  registerIncident(timeoutMs: number): Promise<unknown> {
    if (this.pendingIncident) {
      return Promise.reject(new Error('busy'));
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingIncident = null;
        reject(new Error(`BLE incident timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pendingIncident = { resolve, reject, timer };
    });
  }

  routeResult(value: unknown): boolean {
    if (this.pendingCommand && !this.pendingIncident) {
      const p = this.pendingCommand;
      this.pendingCommand = null;
      clearTimeout(p.timer);
      p.resolve(value);
      return true;
    }

    if (this.pendingIncident && !this.pendingCommand) {
      const p = this.pendingIncident;
      this.pendingIncident = null;
      clearTimeout(p.timer);
      p.resolve(value);
      return true;
    }

    if (this.pendingCommand && this.pendingIncident) {
      const isCmd = Boolean(value && typeof value === 'object' && ('error' in value || !('id' in value)));
      const p = isCmd ? this.pendingCommand : this.pendingIncident;
      if (isCmd) this.pendingCommand = null;
      else this.pendingIncident = null;
      clearTimeout(p.timer);
      p.resolve(value);
      return true;
    }

    return false;
  }

  rejectAll(error: Error): void {
    if (this.pendingCommand) {
      const p = this.pendingCommand;
      this.pendingCommand = null;
      clearTimeout(p.timer);
      p.reject(error);
    }
    if (this.pendingIncident) {
      const p = this.pendingIncident;
      this.pendingIncident = null;
      clearTimeout(p.timer);
      p.reject(error);
    }
  }

  hasPending(): boolean {
    return Boolean(this.pendingCommand || this.pendingIncident);
  }
}
