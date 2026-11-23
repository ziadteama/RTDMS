import type { PiDrowsiness } from './types';

export function calibrationState(d?: PiDrowsiness): 'done' | 'notDone' | 'inProgress' {
  if (d?.calibration === 'calibrating') return 'inProgress';
  if (d?.calibration != null) return d.calibration === 'ok' ? 'done' : 'notDone';
  return d?.calibrated ? 'done' : 'notDone';
}
