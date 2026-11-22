/**
 * Keeps the Bluetooth link to the paired unit running. Reads the pairing from the stores (name in
 * settings, token in the secure store), starts the link when there is one and we are not in demo
 * mode, stops it otherwise, and remembers the peripheral id once connected so the next start can
 * skip the scan. No timers here: the link owns its own reconnect backoff.
 */
import { getBleLink } from '@/pi/ble';
import { requestBlePermissions } from '@/pi/ble/permissions';
import { setLive } from '@/state/live';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';

/** name + token of the active pairing, or null (demo, or nothing paired over Bluetooth). No token = DEV open link. */
function pairing(): { name: string; token: string | null } | null {
  const { demo, bleName } = useSettings.getState();
  return !demo && bleName ? { name: bleName, token: useSecure.getState().piToken } : null;
}

export function startBleLink(): () => void {
  const link = getBleLink();
  let active = true;
  let wanted: string | null = null;
  let granted = false;

  const evaluate = () => {
    const p = pairing();
    const key = p ? `${p.name}\n${p.token ?? ''}` : '';
    if (key === wanted) return;
    wanted = key;
    if (!p) {
      link.stop();
      setLive({ btOff: false });
      return;
    }
    void begin(key);
  };

  // Ask for the Bluetooth permission before the first start; denied means we simply do not start.
  const begin = async (key: string) => {
    if (!granted) granted = await requestBlePermissions().catch(() => false);
    // The pairing may have changed, or the service stopped, while the dialog was open.
    if (!active || !granted || key !== wanted) return;
    const p = pairing();
    if (p) link.start({ ...p, deviceId: useSettings.getState().bleDeviceId });
  };

  const offState = link.onState((state) => {
    setLive({ btOff: link.btOff });
    const id = link.deviceId;
    if (state === 'online' && id && id !== useSettings.getState().bleDeviceId) useSettings.getState().set({ bleDeviceId: id });
  });
  const offSettings = useSettings.subscribe(evaluate);
  const offSecure = useSecure.subscribe(evaluate);
  evaluate();

  return () => {
    active = false;
    offState();
    offSettings();
    offSecure();
    link.stop();
    setLive({ btOff: false });
  };
}
