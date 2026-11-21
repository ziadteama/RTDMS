import { useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';

import { parseSettings } from '@/pi/parse';
import { isNotSupported } from '@/pi/transport';
import type { PiSettings } from '@/pi/types';
import { pi } from '@/services/pi';

export type PiSettingsState =
  | { kind: 'loading' }
  | { kind: 'unsupported' }
  | { kind: 'error' }
  | { kind: 'ready'; value: PiSettings; saving: boolean };

/**
 * GET /settings when the screen is focused; PUT changes debounced (sliders fire continuously).
 * The UI updates at once; if the PUT fails the Pi's answer on the next load wins.
 */
export function usePiSettings() {
  const [state, setState] = useState<PiSettingsState>({ kind: 'loading' });
  const pending = useRef<Partial<PiSettings>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(() => {
    pi()
      .get('/settings', 3000)
      .then((v) => {
        const s = parseSettings(v);
        setState(s ? { kind: 'ready', value: s, saving: false } : { kind: 'error' });
      })
      .catch((e: unknown) => setState({ kind: isNotSupported(e) ? 'unsupported' : 'error' }));
  }, []);

  useFocusEffect(load);

  const update = useCallback(
    (patch: Partial<PiSettings>) => {
      setState((s) => (s.kind === 'ready' ? { ...s, value: { ...s.value, ...patch, detectors: { ...s.value.detectors, ...(patch.detectors ?? {}) } }, saving: true } : s));
      pending.current = { ...pending.current, ...patch, detectors: { ...(pending.current.detectors ?? {}), ...(patch.detectors ?? {}) } as PiSettings['detectors'] };
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => {
        const body = pending.current;
        pending.current = {};
        pi()
          .send('PUT', '/settings', body)
          .then((v) => {
            const s = parseSettings(v);
            setState((cur) => (s ? { kind: 'ready', value: s, saving: false } : cur.kind === 'ready' ? { ...cur, saving: false } : cur));
          })
          .catch(load);
      }, 400);
    },
    [load],
  );

  return { state, update, reload: load };
}
