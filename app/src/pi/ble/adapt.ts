/** Contract BLE payloads → the HTTP shape consumed by the app parsers. */
import { ALERT_PATTERNS } from '../types';
import type { BleNotifyKind } from './types';

type Obj = Record<string, unknown>;
const object = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const number = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const pick = (v: Obj, keys: string[]): Obj => Object.fromEntries(keys.filter((k) => k in v).map((k) => [k, v[k]]));

export function adaptStatus(v: unknown): Obj | null {
  if (!object(v) || !number(v.fps) || typeof v.face !== 'boolean' || typeof v.state !== 'string' ||
      !['starting', 'unavailable', 'alert', 'distracted', 'warning', 'drowsy'].includes(v.state)) return null;
  return {
    ...pick(v, ['fps', 'face', 'temp_c']),
    drowsiness: pick(v, ['state', 'face', 'perclos', 'openness', 'blink_rate', 'closure_ms', 'calibrated']),
    hybrid: { ...pick(v, ['face', 'call', 'texting']), ...('phone_p' in v ? { p: v.phone_p } : {}) },
  };
}

export function adaptPhysio(v: unknown): Obj | null {
  if (!object(v) || typeof v.watch_connected !== 'boolean' || !number(v.t)) return null;
  return {
    ...pick(v, ['watch_connected', 'hr_bpm', 'rr_ms', 'fatigue_probability', 't']),
    hrv: { state: v.hrv_state, ...pick(v, ['rmssd_ms', 'quality']) },
  };
}

export function adaptAlert(v: unknown): Obj | null {
  if (!object(v) || !ALERT_PATTERNS.some((p) => p === v.pattern) || !number(v.t) ||
      !Array.isArray(v.reasons) || !v.reasons.every((r) => typeof r === 'string')) return null;
  return pick(v, ['pattern', 'reasons', 't']);
}

export const adaptNotify = (kind: BleNotifyKind, value: unknown): Obj | null =>
  kind === 'status' ? adaptStatus(value) : kind === 'physio' ? adaptPhysio(value) : adaptAlert(value);
