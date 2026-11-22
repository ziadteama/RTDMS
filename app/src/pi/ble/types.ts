/**
 * The BLE link contract between the ble-plx side (src/pi/ble/link.ts, fake-link.ts) and the app
 * services (src/services/*). Wire details: contracts/pi-link/CONTRACT.md. Keep this file small.
 */
export type BleState = 'idle' | 'scanning' | 'connecting' | 'online' | 'offline';

/** Notified characteristics the app consumes (01 alert, 02 status, 03 physio). Values are parsed JSON. */
export type BleNotifyKind = 'alert' | 'status' | 'physio';
export type BleNotify = { kind: BleNotifyKind; value: unknown; at: number };

export type BleTarget = {
  /** Advertised name from the QR `B` field, e.g. "RTDMS-Pi". */
  name: string;
  /** QR `K` token, written to characteristic 09 (auth) first after every connect. Omitted for a unit in DEV open mode (no auth write). */
  token?: string | null;
  /** Remembered peripheral id from a previous connect; preferred over scanning. */
  deviceId?: string | null;
};

/** A unit seen while scanning: peripheral id, advertised name, signal in dBm. */
export type BleUnit = { id: string; name: string; rssi: number | null };

export interface BleLink {
  /** Why the last attempt failed: 'auth' (the unit wants a pairing code) or 'connection'; null when fine. */
  readonly lastError: string | null;
  readonly state: BleState;
  /** True while the phone's Bluetooth is switched off; the UI shows "Bluetooth is off". */
  readonly btOff: boolean;
  /** Wall-clock ms of the last notify received, or null. */
  readonly lastNotifyAt: number | null;
  /** Peripheral id of the current/last connection (persist it as the remembered id), or null. */
  readonly deviceId: string | null;
  /** Begin scan/connect and keep reconnecting with backoff until stop(). Idempotent for the same target. */
  start(target: BleTarget): void;
  /** Disconnect, cancel every timer and scan: state becomes 'idle'. No timers may run while idle. */
  stop(): void;
  onState(cb: (state: BleState) => void): () => void;
  onNotify(cb: (n: BleNotify) => void): () => void;
  /** Read 04 settings / 0a health; rejects when not online. */
  read(char: 'settings' | 'health'): Promise<unknown>;
  /** Write a subset to 04 settings (write-with-response). */
  writeSettings(body: unknown): Promise<void>;
  /** Write 05 command and resolve with the next 06 result; rejects on timeout or link loss. */
  command(body: unknown, timeoutMs?: number): Promise<unknown>;
  /** Write 07 incident_request and resolve with the next 06 incident_response; same rules as command(). */
  incident(body: unknown, timeoutMs?: number): Promise<unknown>;
  /** One-shot scan for units advertising `name`, strongest first. Does not touch the running link. */
  scan(name: string, ms?: number): Promise<BleUnit[]>;
  /** Signal strength of the connected peripheral in dBm, or null. */
  readRssi(): Promise<number | null>;
}
