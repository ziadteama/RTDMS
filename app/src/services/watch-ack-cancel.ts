import { db } from '@/state/db';
import { useLive } from '@/state/live';

import { cancelSos } from './emergency';

/** Match Pi safety: ack_age_s ≤ 2 s counts as a fresh watch "I'm OK". */
export const WATCH_ACK_FRESH_S = 2;

/**
 * When the watch ACK is fresh, cancel any pending SOS countdown the same way as "I'm OK" on
 * the phone. Edge-triggered so a held ACK does not re-fire.
 */
export function startWatchAckCancel(): () => void {
  let armed = true;
  const check = () => {
    const age = useLive.getState().physio?.ack_age_s;
    const fresh = age != null && age <= WATCH_ACK_FRESH_S;
    if (!fresh) {
      armed = true;
      return;
    }
    if (!armed) return;
    armed = false;
    for (const incident of db.incidents()) {
      if (incident.outcome === 'pending') cancelSos(incident.id);
    }
  };
  const unsubscribe = useLive.subscribe(check);
  check();
  return unsubscribe;
}

/** True when physio carries a fresh watch ACK (for the SOS screen). */
export function isWatchAckFresh(ackAgeS: number | null | undefined): boolean {
  return ackAgeS != null && ackAgeS <= WATCH_ACK_FRESH_S;
}
