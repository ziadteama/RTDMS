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
    ...pick(v, ['fps', 'face', 'temp_c', 't', 't_src']),
    drowsiness: pick(v, ['state', 'face', 'perclos', 'openness', 'blink_rate', 'closure_ms', 'calibrated', 'calibration',
      'calibration_step', 'calibration_left_s']),
    hybrid: { ...pick(v, ['face', 'call', 'texting']), ...('phone_p' in v ? { p: v.phone_p } : {}) },
  };
}

export function adaptPhysio(v: unknown): Obj | null {
  if (!object(v) || typeof v.watch_connected !== 'boolean' || !number(v.t)) return null;
  return pick(v, ['watch_connected', 'hr_bpm', 'rr_ms', 'hrv_state', 'rmssd_ms', 'quality',
    'worn', 'hr_baseline_bpm', 'hr_delta_bpm', 'hr_trend_bpm_per_10min', 't', 't_src']);
}

export function adaptAlert(v: unknown): Obj | null {
  if (!object(v) || !ALERT_PATTERNS.some((p) => p === v.pattern) || !number(v.t) ||
      !Array.isArray(v.reasons) || !v.reasons.every((r) => typeof r === 'string')) return null;
  return pick(v, ['pattern', 'reasons', 't', 't_src', 'emergency']);
}

export const adaptNotify = (kind: BleNotifyKind, value: unknown): Obj | null =>
  kind === 'status' ? adaptStatus(value) : kind === 'physio' ? adaptPhysio(value) : adaptAlert(value);
