import { DemoTransport, HttpTransport, type PiTransport } from '@/pi/transport';
import { useSettings } from '@/state/settings';

let current: PiTransport | null = null;
let key = '';

/** The transport for the current settings (demo or the configured base URL). */
export function pi(): PiTransport {
  const { demo, baseUrl } = useSettings.getState();
  const k = demo ? 'demo' : baseUrl;
  if (!current || k !== key) {
    current = demo ? new DemoTransport() : new HttpTransport(baseUrl);
    key = k;
  }
  return current;
}
