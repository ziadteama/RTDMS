/**
 * Parsers for Pi responses. Bad or partial input yields null (or a null field), never a guess:
 * the repo-wide rule "bad input → null output" applies to the app too.
 */
import {
  ALERT_PATTERNS,
  type AlertPattern,
  type BehaviourLevel,
  type DrowsinessState,
  type HrvState,
  type ModelState,
  type PiAlert,
  type PiDrowsiness,
  type PiHealth,
  type PiHybrid,
  type PiIncident,
  type PiPhysio,
  type PiSettings,
  type PiStatus,
  type Sensitivity,
  type SignalQuality,
} from './types';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const bool = (v: unknown): boolean => v === true;
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);
const oneOf = <T extends string>(v: unknown, allowed: readonly T[]): T | null =>
  typeof v === 'string' && (allowed as readonly string[]).includes(v) ? (v as T) : null;

function parseTime(v: Obj) {
  const t = num(v.t);
  const source = oneOf(v.t_src, ['phone', 'pi'] as const);
  return { ...(t !== null ? { t } : {}), ...(source ? { t_src: source } : {}) };
}

const DROWSY_STATES: readonly DrowsinessState[] = ['starting', 'unavailable', 'alert', 'distracted', 'warning', 'drowsy'];
const LEVELS: readonly BehaviourLevel[] = ['none', 'warning', 'alert'];

function parseDrowsiness(v: unknown): PiDrowsiness | undefined {
  if (!isObj(v)) return undefined;
  return {
    // An unknown state from a newer Pi is shown as "unavailable", not mapped to a guess.
    state: oneOf(v.state, DROWSY_STATES) ?? 'unavailable',
    reasons: strs(v.reasons),
    perclos: num(v.perclos),
    perclos_valid: bool(v.perclos_valid),
    blink_rate: num(v.blink_rate),
    closure_ms: num(v.closure_ms) ?? 0,
    openness: num(v.openness),
    face: bool(v.face),
    calibrated: bool(v.calibrated),
    message: str(v.message) ?? '',
    ms: num(v.ms) ?? 0,
  };
}

function parseHybrid(v: unknown): PiHybrid | undefined {
  if (!isObj(v)) return undefined;
  return {
    face: bool(v.face),
    call: bool(v.call),
    texting: bool(v.texting),
    action: str(v.action),
    p: num(v.p),
    ear: num(v.ear),
    lap: num(v.lap),
  };
}

/** GET /status (stream.py). Returns null when the required core fields are missing. */
export function parseStatus(v: unknown): PiStatus | null {
  if (!isObj(v)) return null;
  const fps = num(v.fps);
  if (fps === null || typeof v.face !== 'boolean') return null;
  const levels: Record<string, BehaviourLevel> = {};
  if (isObj(v.levels))
    for (const [k, l] of Object.entries(v.levels)) {
      const level = oneOf(l, LEVELS);
      if (level) levels[k] = level;
    }
  const ms: Record<string, number> = {};
  if (isObj(v.ms))
    for (const [k, m] of Object.entries(v.ms)) {
      const n = num(m);
      if (n !== null) ms[k] = n;
    }
  const out: PiStatus = { ...parseTime(v), fps, face: v.face, baseline: num(v.baseline) ?? 0, levels, ms };
  if ('temp_c' in v) out.temp_c = num(v.temp_c);
  const d = parseDrowsiness(v.drowsiness);
  if (d) out.drowsiness = d;
  const h = parseHybrid(v.hybrid);
  if (h) out.hybrid = h;
  return out;
}

export function parseAlert(v: unknown): PiAlert | null {
  if (!isObj(v)) return null;
  const pattern = oneOf<AlertPattern>(v.pattern, ALERT_PATTERNS);
  if (!pattern || num(v.t) === null || !Array.isArray(v.reasons) || !v.reasons.every((r) => typeof r === 'string')) return null;
  return { pattern, reasons: strs(v.reasons), ...parseTime(v), t: num(v.t)!,
    ...(v.emergency === 'unresponsive' ? { emergency: 'unresponsive' as const } : {}) };
}

const HRV_STATES: readonly HrvState[] = ['warmup', 'valid', 'degraded', 'bad', 'stale'];
const QUALITIES: readonly SignalQuality[] = ['good', 'degraded', 'bad'];

export function parsePhysio(v: unknown): PiPhysio | null {
  if (!isObj(v)) return null;
  if (typeof v.watch_connected !== 'boolean' || num(v.t) === null) return null;
  return {
    watch_connected: v.watch_connected,
    hr_bpm: num(v.hr_bpm),
    rr_ms: Array.isArray(v.rr_ms) ? v.rr_ms.map(num).filter((x): x is number => x !== null) : [],
    worn: typeof v.worn === 'boolean' ? v.worn : null,
    hr_baseline_bpm: num(v.hr_baseline_bpm),
    hr_delta_bpm: num(v.hr_delta_bpm),
    hr_trend_bpm_per_10min: num(v.hr_trend_bpm_per_10min),
    quality: oneOf(v.quality, QUALITIES),
    hrv_state: oneOf(v.hrv_state, HRV_STATES),
    rmssd_ms: num(v.rmssd_ms),
    ...parseTime(v),
    t: num(v.t)!,
  };
}

const MODEL_STATES: readonly ModelState[] = ['running', 'off', 'error'];

export function parseHealth(v: unknown): PiHealth | null {
  if (!isObj(v)) return null;
  const cpu = num(v.cpu_pct);
  if (cpu === null) return null;
  const models: Record<string, ModelState> = {};
  if (isObj(v.models))
    for (const [k, s] of Object.entries(v.models)) models[k] = oneOf(s, MODEL_STATES) ?? 'error';
  return {
    ...(isObj(v.physio_diag) ? { physio_diag: Object.fromEntries(
      ['watch_offset_spread_ms', 'late_packets', 'shadow_agree', 'shadow_disagree', 'shadow_only']
        .filter((key) => key in (v.physio_diag as Obj)).map((key) => [key, num((v.physio_diag as Obj)[key])]),
    ) } : {}),
    cpu_pct: cpu,
    temp_c: num(v.temp_c),
    throttled: num(v.throttled) ?? 0,
    volts_5v: num(v.volts_5v),
    fps: num(v.fps) ?? 0,
    uptime_s: num(v.uptime_s) ?? 0,
    mem_used_mb: num(v.mem_used_mb) ?? 0,
    mem_total_mb: num(v.mem_total_mb) ?? 0,
    disk_free_mb: num(v.disk_free_mb) ?? 0,
    disk_total_mb: num(v.disk_total_mb) ?? 0,
    camera: v.camera === 'ok' ? 'ok' : 'lost',
    models,
  };
}

const SENSITIVITIES: readonly Sensitivity[] = ['low', 'normal', 'high'];

export function parseSettings(v: unknown): PiSettings | null {
  if (!isObj(v) || !isObj(v.detectors)) return null;
  const sensitivity = oneOf(v.sensitivity, SENSITIVITIES);
  const eye = num(v.eye_closure_s);
  const gaze = num(v.offroad_gaze_s);
  const phone = num(v.phone_s);
  if (!sensitivity || eye === null || gaze === null || phone === null) return null;
  const d = v.detectors;
  return {
    profile: str(v.profile) ?? 'default',
    profiles: strs(v.profiles),
    sensitivity,
    eye_closure_s: eye,
    offroad_gaze_s: gaze,
    phone_s: phone,
    detectors: {
      drowsiness: bool(d.drowsiness),
      distraction: bool(d.distraction),
      phone: bool(d.phone),
      physiology: bool(d.physiology),
    },
  };
}

export function parseIncidents(v: unknown): PiIncident[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((i): PiIncident[] => {
    if (!isObj(i)) return [];
    const id = str(i.id);
    const t = num(i.t_crash);
    if (!id || t === null) return [];
    return [
      {
        id,
        t_crash: t,
        g_peak: num(i.g_peak) ?? 0,
        lat: num(i.lat),
        lon: num(i.lon),
        duration_s: num(i.duration_s) ?? 0,
        clip_ready: bool(i.clip_ready),
      },
    ];
  });
}

/** `vcgencmd get_throttled` bits (Raspberry Pi firmware). Decoding only, no judgement. */
export function decodeThrottled(mask: number) {
  const bit = (b: number) => (mask & (1 << b)) !== 0;
  return {
    underVoltageNow: bit(0),
    freqCappedNow: bit(1),
    throttledNow: bit(2),
    softTempLimitNow: bit(3),
    underVoltageOccurred: bit(16),
    freqCappedOccurred: bit(17),
    throttledOccurred: bit(18),
    softTempLimitOccurred: bit(19),
  };
}

export type PairingInfo = {
  ssid: string | null;
  password: string | null;
  baseUrl: string;
  /** Advertised BLE name (`B`), null when absent or invalid. */
  bleName: string | null;
  /** Pairing token (`K`, >= 16 chars), null when absent or too short. */
  token: string | null;
  /** Contract version (`V`), null when absent or not a number. */
  version: number | null;
};

/** BLE name limit (advertising payload) and the token floor from contracts/pi-link. */
export const BLE_NAME_MAX = 29;
export const BLE_TOKEN_MIN = 16;
export const validBleName = (v: string | null | undefined): string | null => {
  const n = v?.trim() ?? '';
  return n.length > 0 && n.length <= BLE_NAME_MAX ? n : null;
};
export const validBleToken = (v: string | null | undefined): string | null => {
  const k = v?.trim() ?? '';
  return k.length >= BLE_TOKEN_MIN ? k : null;
};

/**
 * The Pi's QR code: a standard Wi-Fi QR plus `U:` (API base URL), `B:` (BLE name), `K:` (pairing
 * token) and `V:` (contract version), e.g.
 * `WIFI:T:WPA;S:RTDMS-Pi;P:secret;U:http://10.42.0.1:8080;B:RTDMS-Pi;K:<token>;V:1;;`. Any phone
 * camera can join the hotspot from it; Sahi also reads the rest. A QR with `B` and `K` but no `S`
 * is a Bluetooth-only pairing. A bare `http(s)://` URL is accepted too.
 */
export function parseQr(text: string, defaultBaseUrl: string): PairingInfo | null {
  const s = text.trim();
  const noBle = { bleName: null, token: null, version: null };
  if (/^https?:\/\/[^\s]+$/i.test(s)) return { ssid: null, password: null, baseUrl: s.replace(/\/+$/, ''), ...noBle };
  if (!s.startsWith('WIFI:')) return null;
  const fields: Record<string, string> = {};
  // Fields are `K:value;` with `\` escaping `;`, `,`, `:`, `\` and `"`.
  const re = /([A-Z]):((?:\\.|[^;])*);/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s.slice(5))) !== null) fields[m[1]!] = m[2]!.replace(/\\(.)/g, '$1');
  const ssid = fields.S ?? null;
  const bleName = validBleName(fields.B);
  const token = validBleToken(fields.K);
  if (!ssid && !(bleName && token)) return null;
  const url = fields.U && /^https?:\/\//i.test(fields.U) ? fields.U.replace(/\/+$/, '') : defaultBaseUrl;
  const version = fields.V !== undefined && /^\d+$/.test(fields.V) ? Number(fields.V) : null;
  return { ssid, password: fields.P ?? null, baseUrl: url, bleName, token, version };
}

/** Normalize a typed base URL: add http://, drop trailing slashes. null if it cannot be a URL. */
export function normalizeBaseUrl(input: string): string | null {
  let s = input.trim();
  if (!s) return null;
  if (!/^https?:\/\//i.test(s)) s = `http://${s}`;
  s = s.replace(/\/+$/, '');
  return /^https?:\/\/[A-Za-z0-9.\-[\]:]+(:\d+)?(\/.*)?$/.test(s) ? s : null;
}
