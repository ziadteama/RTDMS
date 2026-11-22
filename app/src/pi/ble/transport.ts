/**
 * Hybrid transport: handles control, sensor notifies, calibration, alert tests,
 * and incidents over BLE (BleLink), delegating large media (streams, clips, frames)
 * to HttpTransport.
 */

import { type ClipSource, PiHttpError, type PiTransport } from '../transport';
import type { IncidentFrame } from '../types';
import { adaptNotify } from './adapt';
import type { BleLink, BleNotifyKind } from './types';

export class BleTransport implements PiTransport {
  readonly kind = 'ble';
  private readonly cached: Partial<Record<BleNotifyKind, unknown>> = {};
  private readonly unsubNotify: () => void;

  constructor(
    readonly link: BleLink,
    readonly http: PiTransport,
  ) {
    this.unsubNotify = this.link.onNotify((n) => {
      this.cached[n.kind] = n.value;
    });
  }

  dispose(): void {
    this.unsubNotify();
  }

  async get(path: string, timeoutMs?: number): Promise<unknown> {
    switch (path) {
      case '/status':
      case '/alert':
      case '/physio': {
        const kind = path.slice(1) as BleNotifyKind;
        const val = this.cached[kind];
        if (val === undefined) {
          throw new Error(`BLE transport: no cached ${kind} notify received yet`);
        }
        return adaptNotify(kind, val);
      }
      case '/health':
        return this.link.read('health');
      case '/settings':
        return this.link.read('settings');
      default:
        return this.http.get(path, timeoutMs);
    }
  }

  async send(method: 'POST' | 'PUT', path: string, body?: unknown, timeoutMs?: number): Promise<unknown> {
    if (method === 'PUT' && path === '/settings') {
      await this.link.writeSettings(body);
      return this.link.read('settings');
    }

    if (method === 'POST') {
      if (path === '/system/restart' || path === '/system/shutdown') {
        const res = await this.link.command({ cmd: path.slice('/system/'.length) }, timeoutMs);
        if (res && typeof res === 'object' && 'ok' in res && res.ok === false) throw new PiHttpError(400, path);
        return res;
      }

      if (path === '/test_alert') {
        const b = (body ?? {}) as Record<string, unknown>;
        const cmd = { cmd: 'test_alert', ...b };
        const res = (await this.link.command(cmd, timeoutMs)) as { ok?: boolean; error?: string } | null;
        if (res && res.ok === false) throw new PiHttpError(400, path);
        return res;
      }

      if (path === '/calibrate') {
        const b = (body ?? {}) as Record<string, unknown>;
        const hasBody = typeof b === 'object' && b !== null && Object.keys(b).length > 0;
        const cmd: Record<string, unknown> = { cmd: 'calibrate' };
        if (hasBody) {
          cmd.profile = 'profile' in b ? b.profile : b;
        }
        const res = (await this.link.command(cmd, timeoutMs)) as { ok?: boolean; error?: string } | null;
        if (res && res.ok === false) throw new PiHttpError(400, path);
        return res;
      }

      if (path === '/incident') {
        const res = (await this.link.incident(body, timeoutMs)) as { ok?: boolean; error?: string } | null;
        if (res && res.ok === false) throw new PiHttpError(400, path);
        return res;
      }
    }

    return this.http.send(method, path, body, timeoutMs);
  }

  streamUrl(): string | null {
    return this.http.streamUrl();
  }

  clip(incidentId: string): ClipSource {
    return this.http.clip(incidentId);
  }

  frames(incidentId: string): Promise<IncidentFrame[]> {
    return this.http.frames(incidentId);
  }
}
