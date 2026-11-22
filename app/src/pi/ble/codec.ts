/**
 * Compact JSON and Base64 wire codec for BLE characteristic payloads.
 * Size limits: phone writes <= 512 B.
 */

const B64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

export function bytesToBase64(bytes: Uint8Array): string {
  let out = '';
  const len = bytes.length;
  for (let i = 0; i < len; i += 3) {
    const b0 = bytes[i]!;
    const b1 = i + 1 < len ? bytes[i + 1]! : 0;
    const b2 = i + 2 < len ? bytes[i + 2]! : 0;
    out += B64_CHARS[b0 >> 2];
    out += B64_CHARS[((b0 & 3) << 4) | (b1 >> 4)];
    out += i + 1 < len ? B64_CHARS[((b1 & 15) << 2) | (b2 >> 6)] : '=';
    out += i + 2 < len ? B64_CHARS[b2 & 63] : '=';
  }
  return out;
}

export function base64ToBytes(b64: string): Uint8Array | null {
  if (typeof b64 !== 'string') return null;
  const s = b64.trim();
  if (s.length === 0 || s.length % 4 !== 0 || !/^[A-Za-z0-9+/]+={0,2}$/.test(s)) {
    return null;
  }
  try {
    if (typeof globalThis.atob === 'function') {
      const bin = globalThis.atob(s);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) {
        bytes[i] = bin.charCodeAt(i);
      }
      return bytes;
    }
  } catch {
    return null;
  }
  return null;
}

/**
 * Encode an object into compact JSON (UTF-8) and return a Base64 string.
 * Throws if the UTF-8 payload exceeds the 512-byte GATT write limit.
 */
export function encode(obj: unknown): string {
  const json = JSON.stringify(obj);
  const bytes = new TextEncoder().encode(json);
  if (bytes.length > 512) {
    throw new Error(`payload exceeds 512 B limit (${bytes.length} bytes)`);
  }
  return bytesToBase64(bytes);
}

/**
 * Decode a Base64 string containing UTF-8 JSON.
 * Returns parsed value, or null on invalid base64, UTF-8, or JSON. Never throws.
 */
export function decode(b64: unknown): unknown | null {
  if (typeof b64 !== 'string') return null;
  const bytes = base64ToBytes(b64);
  if (!bytes) return null;
  try {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Payload builder for characteristic 09 (auth). */
export function authPayload(token: string, contract?: number): { token: string; contract?: number } {
  return contract !== undefined ? { token, contract } : { token };
}

/** Payload builder for characteristic 08 (clock). Required field: phone_ms. */
export function clockPayload(nowMs: number = Date.now()): { phone_ms: number } {
  return { phone_ms: Math.round(nowMs) };
}

export type CommandType = 'test_alert' | 'calibrate' | 'restart' | 'shutdown';

export type CommandPayloadOptions = {
  pattern?: 'none' | 'short_beep' | 'repeated' | 'continuous' | 'max';
  id?: string;
  profile?: Record<string, unknown>;
};

/** Payload builder for characteristic 05 (command). */
export function commandPayload(
  cmd: CommandType,
  options?: CommandPayloadOptions,
): {
  cmd: CommandType;
  pattern?: 'none' | 'short_beep' | 'repeated' | 'continuous' | 'max';
  id?: string;
  profile?: Record<string, unknown>;
} {
  const payload: {
    cmd: CommandType;
    pattern?: 'none' | 'short_beep' | 'repeated' | 'continuous' | 'max';
    id?: string;
    profile?: Record<string, unknown>;
  } = { cmd };
  if (options?.pattern !== undefined) payload.pattern = options.pattern;
  if (options?.id !== undefined) payload.id = options.id;
  if (options?.profile !== undefined) payload.profile = options.profile;
  return payload;
}

export type IncidentPayloadArgs = {
  t_crash: number;
  g_peak: number;
  lat?: number | null;
  lon?: number | null;
  client_id?: string;
};

/** Payload builder for characteristic 07 (incident_request). */
export function incidentPayload(req: IncidentPayloadArgs): {
  t_crash: number;
  g_peak: number;
  lat?: number | null;
  lon?: number | null;
  client_id?: string;
} {
  const payload: {
    t_crash: number;
    g_peak: number;
    lat?: number | null;
    lon?: number | null;
    client_id?: string;
  } = {
    t_crash: Math.round(req.t_crash),
    g_peak: req.g_peak,
  };
  if (req.lat !== undefined) payload.lat = req.lat;
  if (req.lon !== undefined) payload.lon = req.lon;
  if (req.client_id !== undefined) payload.client_id = req.client_id;
  return payload;
}
