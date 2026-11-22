/**
 * Feeds `useLive` from the Pi. Bluetooth first: while the BLE link is online the unit pushes its
 * data and no HTTP is sent (poller-ble.ts). Otherwise the HTTP poll runs: /status + /alert +
 * /physio at 1 Hz when the unit is paired over Bluetooth (it is only the fallback then, and the
 * phone must not wake the Pi's Wi-Fi at 5 Hz), or /status + /alert at 5 Hz and /physio at 1 Hz
 * when there is no Bluetooth pairing at all (dev against mock-pi, pure Wi-Fi use). Three failures
 * in a row → offline; then it retries every second and, if the phone was paired by QR, re-joins
 * the Pi hotspot every 10 s.
 */
import SahiNative from '@modules/sahi-native';
import { getBleLink } from '@/pi/ble';
import { parseAlert, parsePhysio, parseStatus } from '@/pi/parse';
import { isNotSupported } from '@/pi/transport';
import { setLive, useLive } from '@/state/live';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';

import { pi } from './pi';
import { startBlePush } from './poller-ble';

const FAST_MS = 200;
const FALLBACK_MS = 1000;
const OFFLINE_AFTER = 3;
const UNSUPPORTED_RETRY_MS = 30_000;

/** Paired over Bluetooth (name; the token is optional: DEV open link) and not in demo mode. */
const bleConfigured = () => !useSettings.getState().demo && !!useSettings.getState().bleName;

/** One HTTP polling loop; returns its stop function. A stopped loop never touches the store again. */
function startHttpLoop(): () => void {
  let alive = true;
  let failures = 0;
  let tick = 0;
  let alertRetryAt = 0;
  let physioRetryAt = 0;
  let lastRejoin = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const loop = async () => {
    if (!alive) return;
    const started = Date.now();
    const period = bleConfigured() ? FALLBACK_MS : FAST_MS;
    const transport = pi();
    const live = useLive.getState();
    const wantAlert = live.alertSupported !== false || started > alertRetryAt;
    const wantPhysio = tick % (FALLBACK_MS / period) === 0 && (live.physioSupported !== false || started > physioRetryAt);
    tick++;

    const [s, a, p] = await Promise.allSettled([
      transport.get('/status'),
      wantAlert ? transport.get('/alert') : Promise.resolve(undefined),
      wantPhysio ? transport.get('/physio') : Promise.resolve(undefined),
    ]);
    if (!alive) return;

    const patch: Partial<typeof live> = {};
    const status = s.status === 'fulfilled' ? parseStatus(s.value) : null;
    if (status) {
      failures = 0;
      patch.status = status;
      patch.connection = 'online';
      patch.lastOkAt = Date.now();
      patch.link = transport.kind === 'demo' ? null : 'http';
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

    const wait = failures >= OFFLINE_AFTER ? 1000 : Math.max(0, period - (Date.now() - started));
    timer = setTimeout(loop, wait);
  };

  void loop();
  return () => {
    alive = false;
    if (timer) clearTimeout(timer);
    timer = null;
  };
}

export function startPoller(): () => void {
  const link = getBleLink();
  let stopHttp: (() => void) | null = null;
  let stopPush: (() => void) | null = null;

  // Exactly one source at a time: BLE notifications while the link is online, else HTTP.
  const sync = () => {
    const viaBle = bleConfigured() && link.state === 'online';
    if (viaBle && !stopPush) {
      stopHttp?.();
      stopHttp = null;
      stopPush = startBlePush(link);
    } else if (!viaBle && !stopHttp) {
      stopPush?.();
      stopPush = null;
      stopHttp = startHttpLoop();
    }
  };

  const offState = link.onState(sync);
  sync();
  return () => {
    offState();
    stopHttp?.();
    stopPush?.();
    stopHttp = stopPush = null;
    setLive({ connection: 'connecting', link: null, status: null, alert: null, physio: null, alertSupported: null, physioSupported: null });
  };
}
