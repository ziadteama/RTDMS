import type { BleLink } from '@/pi/ble/types';
import { parseStatus } from '@/pi/parse';
import { HttpTransport } from '@/pi/transport';

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
 * the subscription and the timer (call it when another check already decided).
 */
export function waitBleOnline(link: BleLink, ms = 10_000): { done: Promise<boolean>; cancel: () => void } {
  let cancel = () => {};
  const done = new Promise<boolean>((resolve) => {
    if (link.state === 'online') return resolve(true);
    const off = link.onState((s) => {
      if (s === 'online') finish(true);
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
