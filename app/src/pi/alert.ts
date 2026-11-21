/**
 * How the app presents what the Pi decided. Two inputs, both already decisions made on the Pi:
 *  - fusion's AlertPattern (GET /alert) → color, notification, voice, haptics
 *  - the models' categorical states in /status (drowsiness.state, hybrid.call / texting) → the
 *    label on the state indicator
 * Nothing here compares a model score with a threshold: fusion owns that.
 */
import { ALERT_PATTERNS, type AlertPattern, type PiStatus } from './types';

export const severity = (p: AlertPattern): number => ALERT_PATTERNS.indexOf(p);

export const isEscalation = (from: AlertPattern | null, to: AlertPattern): boolean =>
  severity(to) > severity(from ?? 'none');

export type HapticKind = 'none' | 'tap' | 'warning' | 'error';

export type AlertPresentation = {
  /** Post a phone notification when this pattern starts (the Pi buzzer sounds at the same time). */
  notify: boolean;
  /** Speak the voice line when the pattern starts, and again every `repeatMs` while it lasts. */
  voice: boolean;
  repeatMs: number | null;
  haptic: HapticKind;
  /** Pulse the state indicator (disabled under reduce motion). */
  pulse: boolean;
};

/** Mirrors the report's alert ladder (§ Alert generation) one-to-one. */
export const ALERT_PRESENTATION: Record<AlertPattern, AlertPresentation> = {
  none: { notify: false, voice: false, repeatMs: null, haptic: 'none', pulse: false },
  short_beep: { notify: true, voice: true, repeatMs: null, haptic: 'tap', pulse: false },
  repeated: { notify: true, voice: true, repeatMs: 8000, haptic: 'warning', pulse: false },
  continuous: { notify: true, voice: true, repeatMs: 5000, haptic: 'error', pulse: false },
  max: { notify: true, voice: true, repeatMs: 4000, haptic: 'error', pulse: true },
};

export type DriverState =
  | 'offline'
  | 'starting'
  | 'noFace'
  | 'attentive'
  | 'distracted'
  | 'warning'
  | 'drowsy'
  | 'phone';

/** Label for the state indicator, from the Pi's own categorical outputs. */
export function driverState(status: PiStatus | null, online: boolean): DriverState {
  if (!online || !status) return 'offline';
  const h = status.hybrid;
  if (h && (h.call || h.texting)) return 'phone';
  const d = status.drowsiness;
  if (d) {
    switch (d.state) {
      case 'drowsy':
        return 'drowsy';
      case 'warning':
        return 'warning';
      case 'distracted':
        return 'distracted';
      case 'unavailable':
        return 'noFace';
      case 'starting':
        return 'starting';
      case 'alert':
        return 'attentive';
    }
  }
  // stream.py without --drowsiness: the release rules report per-behaviour levels.
  if (Object.values(status.levels).some((l) => l !== 'none')) return 'distracted';
  return status.face ? 'attentive' : 'noFace';
}

/** Voice line key per pattern + state; the line names what the driver should do. */
export function voiceKey(pattern: AlertPattern, state: DriverState): string | null {
  if (pattern === 'none') return null;
  if (state === 'phone') return 'voice.phone';
  if (state === 'drowsy' || state === 'warning') return pattern === 'max' ? 'voice.max' : 'voice.drowsy';
  if (state === 'distracted' || state === 'noFace') return 'voice.distracted';
  return pattern === 'max' ? 'voice.max' : 'voice.generic';
}
