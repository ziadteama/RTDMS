import type { PhoneCalibrationPayload } from '@/calibration/types';
import { getBleLink } from '@/pi/ble';
import { useLive } from '@/state/live';
import { useSettings } from '@/state/settings';

export type CalibrationSyncStatus = 'ok' | 'rejected' | 'unreachable';

export type CalibrationTransport = {
  send(payload: PhoneCalibrationPayload): Promise<CalibrationSyncStatus>;
};

/** Plain Wi-Fi/HTTP path: POST /calibrate with the profile as the body. */
export class HttpCalibrationTransport implements CalibrationTransport {
  constructor(private getBaseUrl: () => string = () => useSettings.getState().baseUrl) {}

  async send(payload: PhoneCalibrationPayload): Promise<CalibrationSyncStatus> {
    const baseUrl = this.getBaseUrl();
    try {
      const res = await fetch(`${baseUrl}/calibrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(4000),
      });
      if (res.status === 200 || res.ok) {
        return 'ok';
      }
      if (res.status === 408 || res.status === 429) {
        return 'unreachable';
      }
      if (res.status >= 400 && res.status < 500) {
        return 'rejected';
      }
      return 'unreachable';
    } catch {
      return 'unreachable';
    }
  }
}

/**
 * Bluetooth path: the profile travels in a `calibrate` command on characteristic 05 and the answer
 * is the next command_result on 06 (contracts/pi-link). ok:true -> 'ok', ok:false -> 'rejected',
 * a timeout or link loss -> 'unreachable' (retried on the next reconnect).
 */
export class BleCalibrationTransport implements CalibrationTransport {
  async send(payload: PhoneCalibrationPayload): Promise<CalibrationSyncStatus> {
    try {
      const result = await getBleLink().command({ cmd: 'calibrate', profile: payload });
      if (typeof result === 'object' && result !== null && 'ok' in result) return result.ok === true ? 'ok' : 'rejected';
      return 'rejected';
    } catch {
      return 'unreachable';
    }
  }
}

/** Bluetooth while the link is online, otherwise HTTP. Chosen per send, not at start-up. */
export function defaultCalibrationTransport(): CalibrationTransport {
  return {
    send: (payload) =>
      (getBleLink().state === 'online' ? new BleCalibrationTransport() : new HttpCalibrationTransport()).send(payload),
  };
}

export let lastError: string | null = null;
let lastRejectedAt: number | null = null;

export function getCalibrationSyncError(): string | null {
  return lastError;
}

export function clearCalibrationSyncState(): void {
  lastError = null;
  lastRejectedAt = null;
}

/**
 * Synchronizes phone eye calibration to the Pi unit.
 * Only syncs if:
 * 1. eyeCalibration exists and syncedAt is null.
 * 2. unit is online (connection === 'online').
 * 3. Not in demo mode (demo mode sends nothing and never marks synced).
 * 4. The current calibration was not already rejected with 400.
 *
 * 200 => syncedAt = now
 * 400 => rejected: does not retry same payload forever, exposes lastError
 * network error => retry later on reconnect
 */
export async function syncEyeCalibration(
  transport: CalibrationTransport = defaultCalibrationTransport(),
): Promise<CalibrationSyncStatus | 'skipped'> {
  const { demo, eyeCalibration } = useSettings.getState();
  if (demo) {
    return 'skipped';
  }
  if (!eyeCalibration || eyeCalibration.syncedAt !== null) {
    return 'skipped';
  }
  if (useLive.getState().connection !== 'online') {
    return 'skipped';
  }
  if (lastRejectedAt === eyeCalibration.at) {
    // Already rejected with 400: do NOT retry the same payload forever
    return 'rejected';
  }

  const payload: PhoneCalibrationPayload = {
    source: 'phone',
    closed_ratio: eyeCalibration.closedRatio,
    ear_open: eyeCalibration.earOpen,
    ear_closed: eyeCalibration.earClosed,
    snr: eyeCalibration.snr,
    quality: eyeCalibration.quality,
    samples_open: eyeCalibration.samplesOpen ?? 100,
    samples_closed: eyeCalibration.samplesClosed ?? 30,
    created: eyeCalibration.at,
  };

  const result = await transport.send(payload);

  if (result === 'ok') {
    useSettings.getState().setEyeCalibration({
      ...eyeCalibration,
      syncedAt: Date.now(),
    });
    lastError = null;
    lastRejectedAt = null;
  } else if (result === 'rejected') {
    lastError = 'rejected: calibration invalid or poor quality';
    lastRejectedAt = eyeCalibration.at;
  } else {
    lastError = 'unreachable: network error';
  }

  return result;
}

/**
 * Triggers syncEyeCalibration at app start and listens to live connection changes,
 * retrying automatically when the unit reconnects to 'online'.
 */
export function startCalibrationSync(
  transport?: CalibrationTransport,
): () => void {
  void syncEyeCalibration(transport).catch(() => {});

  const unsub = useLive.subscribe((state, prev) => {
    if (state.connection === 'online' && prev.connection !== 'online') {
      void syncEyeCalibration(transport).catch(() => {});
    }
  });

  return unsub;
}
