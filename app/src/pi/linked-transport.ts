/**
 * Bluetooth first, HTTP fallback: the transport the app uses once a unit was paired over BLE.
 * While the link is online, get/send go over BLE (BleTransport); otherwise over HTTP. Video and
 * incident files are always HTTP (they need Wi-Fi anyway).
 */
import { BleTransport } from './ble/transport';
import type { BleLink } from './ble/types';
import { type ClipSource, HttpTransport, PiHttpError, type PiTransport } from './transport';
import type { IncidentFrame } from './types';

export class LinkedTransport implements PiTransport {
  private readonly http: HttpTransport;
  private readonly ble: BleTransport;

  constructor(
    baseUrl: string,
    private readonly link: BleLink,
  ) {
    this.http = new HttpTransport(baseUrl);
    this.ble = new BleTransport(link, this.http);
  }

  get kind(): 'http' | 'ble' {
    return this.link.state === 'online' ? 'ble' : 'http';
  }

  get(path: string, timeoutMs?: number): Promise<unknown> {
    return this.route((t) => t.get(path, timeoutMs));
  }

  send(method: 'POST' | 'PUT', path: string, body?: unknown, timeoutMs?: number): Promise<unknown> {
    return this.route((t) => t.send(method, path, body, timeoutMs));
  }

  streamUrl() {
    return this.http.streamUrl();
  }

  clip(incidentId: string): ClipSource {
    return this.http.clip(incidentId);
  }

  frames(incidentId: string): Promise<IncidentFrame[]> {
    return this.http.frames(incidentId);
  }

  /** Release the BLE transport's subscriptions. Call when this transport is replaced. */
  dispose() {
    this.ble.dispose();
  }

  /**
   * Online: BLE. A rejection that is not an HTTP status (link lost mid-call, notify missing) is
   * retried ONCE over HTTP; a PiHttpError is a real answer from the Pi and is passed on.
   */
  private async route(call: (t: PiTransport) => Promise<unknown>): Promise<unknown> {
    if (this.link.state !== 'online') return call(this.http);
    try {
      return await call(this.ble);
    } catch (e) {
      if (e instanceof PiHttpError) throw e;
      return call(this.http);
    }
  }
}
