import { getBleLink } from '@/pi/ble';
import type { BleLink, BleUnit } from '@/pi/ble/types';
import { parseStatus } from '@/pi/parse';
import { HttpTransport } from '@/pi/transport';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';

/** Pairing succeeds when the unit answers /status over Wi-Fi (3 tries, 1 s apart). */
export async function httpReachable(baseUrl: string): Promise<boolean> {
  const tr = new HttpTransport(baseUrl);
  for (let i = 0; i < 3; i++) {
    try {
      if (parseStatus(await tr.get('/status', 2500))) return true;
    } catch {
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
  return false;
}

/**
 * Resolves true when the link reaches `online` within `ms`, false on timeout. `cancel()` removes
 * the subscription and the timer (call it when another check already decided). With `failOnAuth` a
 * rejection by the unit (it wants a pairing code) ends the wait at once instead of after `ms`.
 */
export function waitBleOnline(link: BleLink, ms = 10_000, failOnAuth = false): { done: Promise<boolean>; cancel: () => void } {
  let cancel = () => {};
  const done = new Promise<boolean>((resolve) => {
    if (link.state === 'online') return resolve(true);
    const off = link.onState((s) => {
      if (s === 'online') finish(true);
      else if (failOnAuth && s === 'offline' && link.lastError === 'auth') finish(false);
    });
    const timer = setTimeout(() => finish(false), ms);
    function finish(ok: boolean) {
      clearTimeout(timer);
      off();
      resolve(ok);
    }
    cancel = () => finish(false);
  });
  return { done, cancel };
}

/** True as soon as one check is true; false once all of them are false. */
export function firstTrue(checks: Promise<boolean>[]): Promise<boolean> {
  return new Promise((resolve) => {
    let left = checks.length;
    if (left === 0) return resolve(false);
    for (const c of checks)
      void c.then((ok) => {
        if (ok) resolve(true);
        else if (--left === 0) resolve(false);
      });
  });
}

export type OpenPairResult = 'ok' | 'needs-code' | 'unreachable';

/**
 * DEV open pairing: save the unit (name + remembered id, NO token) and wait for the link to come
 * online. The saved pairing starts the background link. If the unit rejects us because it wants a
 * pairing code, or does not answer, the previous pairing is put back and the reason is returned.
 */
export async function pairOpen(unit: BleUnit, link: BleLink = getBleLink(), ms = 10_000): Promise<OpenPairResult> {
  const before = { name: useSettings.getState().bleName, id: useSettings.getState().bleDeviceId, token: useSecure.getState().piToken };
  const wait = waitBleOnline(link, ms, true);
  useSecure.getState().setPiToken(null);
  useSettings.getState().set({ bleName: unit.name, bleDeviceId: unit.id, demo: false });
  const ok = await wait.done;
  if (ok) return 'ok';
  const needsCode = link.lastError === 'auth';
  useSecure.getState().setPiToken(before.token);
  useSettings.getState().set({ bleName: before.name, bleDeviceId: before.id });
  return needsCode ? 'needs-code' : 'unreachable';
}
