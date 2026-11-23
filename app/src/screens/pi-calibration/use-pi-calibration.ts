import { useEffect, useReducer, useRef } from 'react';

import { speak } from '@/services/alerts';
import { pi } from '@/services/pi';
import { setLive, useLive } from '@/state/live';

import { initial, reduce, RESPONSE_TIMEOUT_MS, RUN_TIMEOUT_MS, stepCopy } from './machine';

export function usePiCalibration() {
  const [state, dispatch] = useReducer(reduce, initial);
  const active = useRef(false);
  const run = useRef(0);
  const online = useLive((s) => s.connection === 'online');
  const running = state.phase === 'starting' || state.phase === 'following';
  useEffect(() => useLive.subscribe((next, prev) => {
    if (active.current && next.status !== prev.status) dispatch({ type: 'status', value: next.status?.drowsiness });
  }), []);
  useEffect(() => {
    setLive({ calibrating: running });
    if (!running) { active.current = false; return; }
    const response = setTimeout(() => dispatch({ type: 'no-response' }), RESPONSE_TIMEOUT_MS);
    const cap = setTimeout(() => dispatch({ type: 'fail' }), RUN_TIMEOUT_MS);
    return () => { clearTimeout(response); clearTimeout(cap); };
  }, [running]);
  const { phase, step } = state;
  useEffect(() => {
    if (phase === 'done') speak('cal.done');
    if (phase === 'failed') speak('cal.failed');
    // Speak when the unit starts a countdown (or waits for the face): once per prompt, ahead of it.
    if (phase === 'following' && (step === 'waiting_face' || step === 'countdown_open' || step === 'countdown_closed')) speak(stepCopy[step]);
  }, [phase, step]);
  useEffect(() => () => { active.current = false; run.current += 1; setLive({ calibrating: false }); }, []);
  const start = async () => {
    if (active.current || !online) return;
    active.current = true;
    setLive({ calibrating: true });
    const attempt = ++run.current;
    dispatch({ type: 'start' });
    try {
      await pi().send('POST', '/calibrate');
    } catch {
      if (active.current && attempt === run.current) dispatch({ type: 'fail' });
    }
  };
  return { ...state, online, start };
}
