import { db } from '@/state/db';
import { useLive } from '@/state/live';

import { triggerSos } from './emergency';

/** Missing/offline data does not end an episode; only a subsequent clear alert does. */
export function startUnresponsiveMonitor(): () => void {
  let episode = false;
  const check = () => {
    const { alert, connection } = useLive.getState();
    if (connection !== 'online' || !alert) return;
    if (!alert.emergency) { episode = false; return; }
    if (episode) return;
    episode = true;
    const running = db.incidents().some((i) => i.kind === 'unresponsive' && i.outcome === 'pending');
    if (!running) triggerSos('unresponsive');
  };
  const unsubscribe = useLive.subscribe(check);
  check();
  return unsubscribe;
}
