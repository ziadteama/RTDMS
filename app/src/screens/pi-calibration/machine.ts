import type { PiDrowsiness } from '@/pi/types';

// Matched to the unit's own schedule (distraction/scripts/drowsiness.py + dms_face CalibrationConfig):
// 3 s countdown, 10 s open + 2 s settle, 3 s countdown, 3 s closed + 2 s settle = 23 s with the
// face in view. "Close your eyes" comes at 14 s and lasts past the unit's closed window (18-23 s).
export const OPEN_MS = 14_000;
export const CLOSED_MS = 10_000;
export const RESULT_TIMEOUT_MS = 25_000;
export type Phase = 'intro' | 'open' | 'closed' | 'waiting' | 'done' | 'failed';
type State = { phase: Phase; sawCalibrating: boolean };
type Event = { type: 'start' } | { type: 'tick' } | { type: 'fail' } | { type: 'status'; value?: PiDrowsiness };
export const initial: State = { phase: 'intro', sawCalibrating: false };

export function reduce(state: State, event: Event): State {
  if (event.type === 'start') return { phase: 'open', sawCalibrating: false };
  if (!['open', 'closed', 'waiting'].includes(state.phase)) return state;
  if (event.type === 'fail') return { ...state, phase: 'failed' };
  if (event.type === 'tick') {
    const next = { open: 'closed', closed: 'waiting', waiting: 'failed' } as const;
    return { ...state, phase: next[state.phase as keyof typeof next] };
  }
  const d = event.value;
  // Until the unit reports "calibrating", any result shown is left over from the previous run.
  if (d?.calibration === 'calibrating' || d?.message === 'calibrating') return { ...state, sawCalibrating: true };
  if (!state.sawCalibrating) return state;
  if (d?.message.startsWith('calibration failed') || d?.calibration === 'failed') return { ...state, phase: 'failed' };
  if (d?.message === 'calibrated' || d?.calibration === 'ok') return { ...state, phase: 'done' };
  return state;
}
