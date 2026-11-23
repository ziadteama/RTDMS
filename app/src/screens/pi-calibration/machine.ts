import type { PiDrowsiness } from '@/pi/types';

export const RESPONSE_TIMEOUT_MS = 15_000;
export const RUN_TIMEOUT_MS = 120_000;
export type Phase = 'intro' | 'starting' | 'following' | 'done' | 'failed';
export type Step = PiDrowsiness['calibration_step'];
export type State = { phase: Phase; sawCalibrating: boolean; step: Step; left: number | null };
type Event = { type: 'start' | 'fail' | 'no-response' } | { type: 'status'; value?: PiDrowsiness };
export const initial: State = { phase: 'intro', sawCalibrating: false, step: null, left: null };

export const stepCopy = {
  waiting_face: 'cal.waitingFace', countdown_open: 'cal.step1', open: 'cal.step1',
  countdown_closed: 'cal.step2', closed: 'cal.closed',
} as const;

export function reduce(state: State, event: Event): State {
  if (event.type === 'start') return { ...initial, phase: 'starting' };
  if (state.phase !== 'starting' && state.phase !== 'following') return state;
  if (event.type === 'fail' || (event.type === 'no-response' && state.phase === 'starting')) {
    return { ...state, phase: 'failed' };
  }
  if (event.type !== 'status') return state;
  const d = event.value;
  const calibrating = d?.calibration === 'calibrating' || d?.message === 'calibrating';
  // A step acknowledges Start, but only an explicit calibrating report unlocks results.
  if (calibrating) return {
    phase: 'following', sawCalibrating: true,
    step: d?.calibration_step ?? null, left: d?.calibration_left_s ?? null,
  };
  if (state.sawCalibrating) {
    if (d?.calibration === 'failed' || d?.message.startsWith('calibration failed')) return { ...state, phase: 'failed' };
    if (d?.calibration === 'ok' || d?.message === 'calibrated') return { ...state, phase: 'done' };
  }
  if (d?.calibration_step) return {
    ...state, phase: 'following', step: d.calibration_step, left: d.calibration_left_s,
  };
  return state;
}
