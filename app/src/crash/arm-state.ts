import { DEFAULT_CRASH_CONFIG, type SpeedSample } from './detector';

export const GPS_STALE_MS = 10_000;
export const MOTION_STALE_MS = 1_000;
export type ArmReason = 'armed' | 'disabled' | 'no_gps' | 'too_slow' | 'no_motion';
export const gpsLost = (at: number | null, now: number) => at === null || now - at > GPS_STALE_MS;

/** Phone-only readiness; paused monitoring is disabled. Pi connectivity is irrelevant. */
export function armState(inputs: {
  enabled: boolean; paused: boolean; now: number; gpsAt: number | null;
  motionAt: number | null; speeds: SpeedSample[];
}): { armed: boolean; reason: ArmReason } {
  const { enabled, paused, now, gpsAt, motionAt, speeds } = inputs;
  let reason: ArmReason = 'armed';
  if (!enabled || paused) reason = 'disabled';
  else if (gpsLost(gpsAt, now)) reason = 'no_gps';
  else if (motionAt === null || now - motionAt > MOTION_STALE_MS) reason = 'no_motion';
  else if (!speeds.some((s) => s.t <= now && s.t >= now - DEFAULT_CRASH_CONFIG.armWindowMs &&
    s.kmh !== null && s.kmh > DEFAULT_CRASH_CONFIG.armSpeedKmh)) reason = 'too_slow';
  return { armed: reason === 'armed', reason };
}
