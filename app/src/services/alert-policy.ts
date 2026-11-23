import { ALERT_PRESENTATION, isEscalation } from '@/pi/alert';
import type { AlertPattern } from '@/pi/types';

export type AlertState = { pattern: AlertPattern | null; episode: number | null; voicedAt: number };
export const initialAlertState: AlertState = { pattern: null, episode: null, voicedAt: -Infinity };

/** Pure transition decision; repeated payloads never restart the cadence. */
export function decideAlert(previous: AlertState, pattern: AlertPattern | null, episode: number | null, now: number) {
  const changed = pattern !== previous.pattern || episode !== previous.episode;
  const present = pattern !== null && pattern !== 'none' &&
    ((episode !== null && episode !== previous.episode) || isEscalation(previous.pattern, pattern));
  return {
    changed,
    present,
    stop: changed && (pattern === null || pattern === 'none'),
    state: { pattern, episode, voicedAt: present ? now : previous.voicedAt },
  };
}

export function repeatVoice(state: AlertState, now: number): boolean {
  return state.pattern !== null && ALERT_PRESENTATION[state.pattern].repeatMs !== null && now - state.voicedAt >= 8000;
}
