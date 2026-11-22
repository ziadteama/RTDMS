/**
 * How the app talks to "a Pi": over HTTP (real Pi or mock-pi/server.ts), or in-process for demo
 * mode (the same scenario the mock serves, no network at all).
 */
import {
  SCENARIO_LENGTH_S,
  alertAt,
  healthAt,
  incidentFrames,
  physioAt,
  statusAt,
} from '@/demo/scenario';

import type { AlertPattern, IncidentFrame, IncidentRequest, PiIncident, PiSettings } from './types';

export class PiHttpError extends Error {
  constructor(
    readonly status: number,
    path: string,
  ) {
    super(`${path}: HTTP ${status}`);
  }
}

/** 404 = the Pi runs an older stream.py without this proposed endpoint. */
export const isNotSupported = (e: unknown) => e instanceof PiHttpError && (e.status === 404 || e.status === 501);

export type ClipSource = { uri: string } | { asset: number };

export interface PiTransport {
  readonly kind: 'http' | 'demo' | 'ble';
  get(path: string, timeoutMs?: number): Promise<unknown>;
  send(method: 'POST' | 'PUT', path: string, body?: unknown, timeoutMs?: number): Promise<unknown>;
  /** MJPEG URL for the live view, or null (demo). */
  streamUrl(): string | null;
  clip(incidentId: string): ClipSource;
  frames(incidentId: string): Promise<IncidentFrame[]>;
}

export class HttpTransport implements PiTransport {
  readonly kind = 'http';
  constructor(readonly baseUrl: string) {}

  private async request(method: string, path: string, body: unknown, timeoutMs: number): Promise<unknown> {
    const res = await fetch(this.baseUrl + path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) throw new PiHttpError(res.status, path);
    return res.json();
  }

  get(path: string, timeoutMs = 1500) {
    return this.request('GET', path, undefined, timeoutMs);
  }

  send(method: 'POST' | 'PUT', path: string, body?: unknown, timeoutMs = 4000) {
    return this.request(method, path, body ?? {}, timeoutMs);
  }

  streamUrl() {
    return `${this.baseUrl}/stream.mjpg`;
  }

  clip(id: string): ClipSource {
    return { uri: `${this.baseUrl}/incidents/${encodeURIComponent(id)}/clip.mp4` };
  }

  async frames(id: string): Promise<IncidentFrame[]> {
    const res = await fetch(`${this.baseUrl}/incidents/${encodeURIComponent(id)}/data.jsonl`, {
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) throw new PiHttpError(res.status, '/incidents/data.jsonl');
    const text = await res.text();
    return text
      .split('\n')
      .filter(Boolean)
      .flatMap((l) => {
        try {
          return [JSON.parse(l) as IncidentFrame];
        } catch {
          return [];
        }
      });
  }
}

/** Demo mode: the scripted two-minute drive, answered in-process. */
export class DemoTransport implements PiTransport {
  readonly kind = 'demo';
  private readonly started = Date.now();
  private calibrating: number | null = null;
  private test: { pattern: AlertPattern; until: number } | null = null;
  private incidents: (PiIncident & { tScenario: number })[] = [];
  private settings: PiSettings = {
    profile: 'default',
    profiles: ['default', 'driver-2'],
    sensitivity: 'normal',
    eye_closure_s: 2,
    offroad_gaze_s: 2,
    phone_s: 1,
    detectors: { drowsiness: true, distraction: true, phone: true, physiology: true },
  };

  /** Seconds into the scenario (loops). Also drives demo GPS speed. */
  now(): number {
    return ((Date.now() - this.started) / 1000) % SCENARIO_LENGTH_S;
  }

  async get(path: string): Promise<unknown> {
    const t = this.now();
    switch (path) {
      case '/status': {
        const cal =
          this.calibrating !== null && Date.now() < this.calibrating
            ? { message: 'calibrating', calibrated: true }
            : undefined;
        return statusAt(t, cal);
      }
      case '/alert':
        return this.test && Date.now() < this.test.until
          ? { pattern: this.test.pattern, reasons: ['test alert'], t }
          : alertAt(t);
      case '/physio':
        return physioAt(t);
      case '/health':
        return healthAt(t, (Date.now() - this.started) / 1000 + 3600);
      case '/settings':
        return this.settings;
      case '/incidents':
        return this.incidents.map(({ tScenario: _t, ...i }) => i);
    }
    throw new PiHttpError(404, path);
  }

  async send(method: 'POST' | 'PUT', path: string, body?: unknown): Promise<unknown> {
    const b = (body ?? {}) as Record<string, unknown>;
    if (method === 'PUT' && path === '/settings') {
      const patch = b as Partial<PiSettings>;
      this.settings = { ...this.settings, ...patch, detectors: { ...this.settings.detectors, ...(patch.detectors ?? {}) } };
      return this.settings;
    }
    if (path === '/calibrate') {
      this.calibrating = Date.now() + 13_000;
      return { ok: true };
    }
    if (path === '/test_alert') {
      this.test = { pattern: b.pattern as AlertPattern, until: Date.now() + 3000 };
      return { ok: true };
    }
    if (path === '/incident') {
      const r = b as IncidentRequest;
      const id = new Date(r.t_crash).toISOString().replace(/[:.]/g, '-');
      this.incidents.unshift({ id, ...r, duration_s: 25, clip_ready: true, tScenario: this.now() });
      return { id };
    }
    if (path.startsWith('/system/')) return { ok: true };
    throw new PiHttpError(404, path);
  }

  streamUrl() {
    return null;
  }

  clip(): ClipSource {
    return { asset: require('../../mock-pi/assets/clip.mp4') as number };
  }

  async frames(id: string): Promise<IncidentFrame[]> {
    const i = this.incidents.find((x) => x.id === id);
    return i ? incidentFrames(i.tScenario, i.t_crash) : [];
  }
}
