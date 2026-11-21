/**
 * Trip recorder. A trip starts when the Pi connects and ends after it has been gone for 60 s
 * (short Wi-Fi drops stay in one trip). Everything recorded is a decision the Pi already made:
 * fusion alert onsets, the models' state onsets, eye-closure length and phone use as reported.
 */
import { driverState, isEscalation, type DriverState } from '@/pi/alert';
import type { AlertPattern } from '@/pi/types';
import { db } from '@/state/db';
import { useLive, type LiveState } from '@/state/live';
import { useSettings } from '@/state/settings';
import { EMPTY_SUMMARY, type TripSummary } from '@/trips/model';
import { safetyScore } from '@/trips/score';

const END_AFTER_OFFLINE_MS = 60_000;
const HR_EVERY_MS = 30_000;
const SAVE_EVERY_MS = 10_000;
const LOGGED_STATES: DriverState[] = ['phone', 'drowsy', 'warning', 'distracted', 'noFace'];

let tripId: number | null = null;

/** The trip in progress, for incidents and manual SOS. */
export const currentTripId = () => tripId;

export function startTripManager(): () => void {
  // A trip left open by a killed app is closed at its last recorded moment.
  const stale = db.openTrip();
  if (stale) {
    const end = stale.startedAt + stale.summary.onlineS * 1000;
    db.saveTrip(stale.id, { endedAt: end, score: safetyScore(stale.summary) });
  }

  let summary: TripSummary = structuredClone(EMPTY_SUMMARY);
  let lastAt = 0;
  let lastPattern: AlertPattern | null = null;
  let lastState: DriverState = 'offline';
  let lastHrAt = 0;
  let lastSaveAt = 0;
  let offlineSince: number | null = null;

  const save = () => {
    if (tripId === null) return;
    db.saveTrip(tripId, { summary, score: safetyScore(summary) });
    lastSaveAt = Date.now();
  };

  const end = (at: number) => {
    if (tripId === null) return;
    db.saveTrip(tripId, { endedAt: at, summary, score: safetyScore(summary) });
    tripId = null;
  };

  const onChange = (s: LiveState, prev: LiveState) => {
    const now = Date.now();
    if (s.connection === 'online') {
      if (tripId === null) {
        tripId = db.startTrip(now, useSettings.getState().demo);
        summary = structuredClone(EMPTY_SUMMARY);
        lastAt = now;
        lastPattern = null;
        lastState = 'offline';
      } else if (offlineSince !== null) {
        db.addEvent(tripId, now, 'connected', '');
      }
      offlineSince = null;
    } else if (s.connection === 'offline' && prev.connection === 'online' && tripId !== null) {
      offlineSince = now;
      db.addEvent(tripId, now, 'disconnected', '');
      save();
    }
    if (tripId === null) return;
    if (offlineSince !== null) {
      if (now - offlineSince > END_AFTER_OFFLINE_MS) end(offlineSince);
      return;
    }

    if (s.status !== prev.status && s.status) {
      const dt = Math.min(1000, now - lastAt);
      lastAt = now;
      summary.onlineS += dt / 1000;
      const state = driverState(s.status, true);
      if (state === 'phone') summary.phoneMs += dt;
      const closure = s.status.drowsiness?.closure_ms ?? 0;
      if (closure > summary.longestClosureMs) summary.longestClosureMs = closure;
      if (state !== lastState && LOGGED_STATES.includes(state)) {
        summary.states[state] = (summary.states[state] ?? 0) + 1;
        db.addEvent(tripId, now, 'state', state);
      }
      lastState = state;
    }

    const pattern = s.alert?.pattern ?? null;
    if (pattern !== lastPattern) {
      if (pattern && pattern !== 'none' && isEscalation(lastPattern, pattern)) {
        summary.alerts[pattern]++;
        db.addEvent(tripId, now, 'alert', pattern, s.alert!.reasons.join(', '));
      }
      lastPattern = pattern;
    }

    const bpm = s.physio?.hr_bpm;
    if (bpm != null && now - lastHrAt >= HR_EVERY_MS) {
      lastHrAt = now;
      db.addHr(tripId, now, bpm);
    }
    if (now - lastSaveAt >= SAVE_EVERY_MS) save();
  };

  const unsub = useLive.subscribe(onChange);
  const timer = setInterval(() => onChange(useLive.getState(), useLive.getState()), 5_000);
  return () => {
    unsub();
    clearInterval(timer);
    end(Date.now());
  };
}
