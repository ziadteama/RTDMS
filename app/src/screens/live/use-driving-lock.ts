import { useRef } from 'react';

import { useLive } from '@/state/live';

/** Lock above ~10 km/h, unlock below 7 km/h (hysteresis so it does not flicker at 10). */
export const LOCK_KMH = 10;
const UNLOCK_KMH = 7;

export function useDrivingLock(): boolean {
  const locked = useRef(false);
  return useLive((s) => {
    const v = s.speedKmh ?? 0;
    if (locked.current) locked.current = v >= UNLOCK_KMH;
    else locked.current = v > LOCK_KMH;
    return locked.current;
  });
}
