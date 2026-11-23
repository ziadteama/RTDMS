import { useEffect, useReducer, useRef } from 'react';

import { speak } from '@/services/alerts';
import { pi } from '@/services/pi';
import { useLive } from '@/state/live';

import { CLOSED_MS, initial, OPEN_MS, reduce, RESULT_TIMEOUT_MS } from './machine';

export function usePiCalibration() {
  const [state, dispatch] = useReducer(reduce, initial);
  const active = useRef(false);
  const online = useLive((s) => s.connection === 'online');
  useEffect(() => useLive.subscribe((next, prev) => {
    if (active.current && next.status !== prev.status) dispatch({ type: 'status', value: next.status?.drowsiness });
  }), []);
  const { phase } = state;
  useEffect(() => {
    if (phase === 'done' || phase === 'failed') active.current = false;
    if (phase === 'done') speak('cal.done');
    if (phase === 'open') speak('cal.step1');
    if (phase === 'closed') speak('cal.step2');
    if (phase === 'waiting') speak('cal.waiting');
    const duration = phase === 'open' ? OPEN_MS : phase === 'closed' ? CLOSED_MS : phase === 'waiting' ? RESULT_TIMEOUT_MS : null;
    if (duration === null) return;
    const id = setTimeout(() => dispatch({ type: 'tick' }), duration);
    return () => clearTimeout(id);
  }, [phase]);
  useEffect(() => () => { active.current = false; }, []);
  const start = async () => {
    if (active.current || !online) return;
    active.current = true;
    dispatch({ type: 'start' });
    try {
      await pi().send('POST', '/calibrate');
    } catch {
      if (active.current) dispatch({ type: 'fail' });
    }
  };
  return { phase: state.phase, online, start };
}
