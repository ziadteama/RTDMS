import { getBleLink } from '@/pi/ble';
import { LinkedTransport } from '@/pi/linked-transport';
import { DemoTransport, HttpTransport, type PiTransport } from '@/pi/transport';
import { useSettings } from '@/state/settings';

let current: PiTransport | null = null;
let key = '';

/**
 * The transport for the current settings: demo, plain HTTP to the configured base URL, or (once a
 * unit was paired over Bluetooth) Bluetooth first with the same HTTP address as fallback.
 */
export function pi(): PiTransport {
  const { demo, baseUrl, bleName } = useSettings.getState();
  const k = demo ? 'demo' : `${bleName ? 'ble' : 'http'}:${baseUrl}`;
  if (!current || k !== key) {
    if (current instanceof LinkedTransport) current.dispose();
    current = demo ? new DemoTransport() : bleName ? new LinkedTransport(baseUrl, getBleLink()) : new HttpTransport(baseUrl);
    key = k;
  }
  return current;
}
