/**
 * The Bluetooth half of the poller: while the link is online the unit pushes status, alert and
 * physio notifications and the app sends no HTTP at all. Notifications are written straight into
 * `useLive`, one field at a time and only when the value changed, so a steady drive does not
 * re-render every screen per notify.
 *
 * Battery: there is no interval. One timeout is armed at "last notify + 3 s" (CR v1.2 stale
 * limit); when it fires and nothing arrived meanwhile the unit is marked offline, otherwise it
 * re-arms for the remaining time. `lastOkAt` is written on transitions only; the age of the last
 * notify is `link.lastNotifyAt` (read it where needed instead of subscribing to a store).
 */
import { adaptNotify } from '@/pi/ble/adapt';
import type { BleLink, BleNotify } from '@/pi/ble/types';
import { parseAlert, parsePhysio, parseStatus } from '@/pi/parse';
import { type LiveState, setLive, useLive } from '@/state/live';

export const STALE_MS = 3000;

export function startBlePush(link: BleLink): () => void {
  const startedAt = Date.now();
  const lastRaw: Partial<Record<BleNotify['kind'], string>> = {};
  let timer: ReturnType<typeof setTimeout> | null = null;

  const arm = () => {
    const last = Math.max(link.lastNotifyAt ?? 0, startedAt);
    timer = setTimeout(onStale, Math.max(0, last + STALE_MS - Date.now()));
  };

  function onStale() {
    timer = null;
    const last = Math.max(link.lastNotifyAt ?? 0, startedAt);
    if (Date.now() - last < STALE_MS) return arm();
    for (const k of Object.keys(lastRaw)) delete lastRaw[k as BleNotify['kind']];
    if (useLive.getState().connection !== 'offline') setLive({ connection: 'offline', alert: null, physio: null });
  }

  const off = link.onNotify(({ kind, value }) => {
    const adapted = adaptNotify(kind, value);
    if (!adapted) return;
    const raw = JSON.stringify(kind === 'alert' ? { pattern: adapted.pattern, reasons: adapted.reasons } : adapted);
    const live = useLive.getState();
    const patch: Partial<LiveState> = {};
    if (raw !== lastRaw[kind]) {
      lastRaw[kind] = raw;
      if (kind === 'status') {
        const status = parseStatus(adapted);
        if (status) patch.status = status;
      } else if (kind === 'alert') {
        patch.alert = parseAlert(adapted);
        if (live.alertSupported !== true) patch.alertSupported = true;
      } else {
        patch.physio = parsePhysio(adapted);
        if (live.physioSupported !== true) patch.physioSupported = true;
      }
    }
    if (live.connection !== 'online' || live.link !== 'ble') {
      patch.connection = 'online';
      patch.link = 'ble';
      patch.lastOkAt = Date.now();
    }
    if (Object.keys(patch).length > 0) setLive(patch);
    if (!timer) arm();
  });
  arm();

  return () => {
    off();
    if (timer) clearTimeout(timer);
    timer = null;
  };
}
