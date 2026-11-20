/**
 * Polls the Pi: /status + /alert at 5 Hz, /physio at 1 Hz (spec: no WebSocket until polling is
 * shown to be too slow). Three failures in a row → offline; then retries every second and, if the
 * phone was paired by QR, re-joins the Pi hotspot every 10 s.
 */
import SahiNative from '@modules/sahi-native';
import { parseAlert, parsePhysio, parseStatus } from '@/pi/parse';
import { isNotSupported } from '@/pi/transport';
import { setLive, useLive } from '@/state/live';
import { useSecure } from '@/state/secure';

import { pi } from './pi';

const PERIOD_MS = 200;
const OFFLINE_AFTER = 3;
const UNSUPPORTED_RETRY_MS = 30_000;

export function startPoller(): () => void {
  let running = true;
  let failures = 0;
  let tick = 0;
  let alertRetryAt = 0;
  let physioRetryAt = 0;
  let lastRejoin = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const loop = async () => {
    if (!running) return;
    const started = Date.now();
    const transport = pi();
    const live = useLive.getState();
    const wantAlert = live.alertSupported !== false || started > alertRetryAt;
    const wantPhysio = tick % 5 === 0 && (live.physioSupported !== false || started > physioRetryAt);
    tick++;

    const [s, a, p] = await Promise.allSettled([
      transport.get('/status'),
      wantAlert ? transport.get('/alert') : Promise.resolve(undefined),
      wantPhysio ? transport.get('/physio') : Promise.resolve(undefined),
    ]);
    if (!running) return;

    const patch: Partial<typeof live> = {};
    const status = s.status === 'fulfilled' ? parseStatus(s.value) : null;
    if (status) {
      failures = 0;
      patch.status = status;
      patch.connection = 'online';
      patch.lastOkAt = Date.now();
    } else if (++failures >= OFFLINE_AFTER && live.connection !== 'offline') {
      patch.connection = 'offline';
    }

    if (wantAlert) {
      if (a.status === 'fulfilled') {
        const alert = parseAlert(a.value);
        patch.alert = alert;
        patch.alertSupported = alert !== null;
      } else if (isNotSupported(a.reason)) {
        patch.alertSupported = false;
        patch.alert = null;
        alertRetryAt = Date.now() + UNSUPPORTED_RETRY_MS;
      }
    }
    if (wantPhysio) {
      if (p.status === 'fulfilled') {
        patch.physio = parsePhysio(p.value);
        patch.physioSupported = true;
      } else if (isNotSupported(p.reason)) {
        patch.physioSupported = false;
        patch.physio = null;
        physioRetryAt = Date.now() + UNSUPPORTED_RETRY_MS;
      }
    }
    if (patch.connection === 'offline') {
      patch.alert = null;
      patch.physio = null;
    }
    setLive(patch);

    // Auto reconnect: re-join the Pi hotspot (Android binds the app to it; see sahi-native).
    const wifi = useSecure.getState().wifi;
    if (failures >= OFFLINE_AFTER && wifi && SahiNative && transport.kind === 'http' && Date.now() - lastRejoin > 10_000) {
      lastRejoin = Date.now();
      void SahiNative.joinWifi(wifi.ssid, wifi.password).catch(() => {});
    }

    const wait = failures >= OFFLINE_AFTER ? 1000 : Math.max(0, PERIOD_MS - (Date.now() - started));
    timer = setTimeout(loop, wait);
  };

  void loop();
  return () => {
    running = false;
    if (timer) clearTimeout(timer);
    setLive({ connection: 'connecting', status: null, alert: null, physio: null, alertSupported: null, physioSupported: null });
  };
}
