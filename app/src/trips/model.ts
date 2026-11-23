import type { AlertPattern } from '@/pi/types';
import type { DriverState } from '@/pi/alert';
import type { CrashChecks } from '@/crash/detector';

export type TripSummary = {
  /** Alert onsets per fusion pattern. */
  alerts: Record<Exclude<AlertPattern, 'none'>, number>;
  /** Driver-state onsets (phone, drowsy, distracted, …). */
  states: Partial<Record<DriverState, number>>;
  longestClosureMs: number;
  phoneMs: number;
  /** Seconds online with the Pi (for the per-hour score). */
  onlineS: number;
};

export const EMPTY_SUMMARY: TripSummary = {
  alerts: { short_beep: 0, repeated: 0, continuous: 0, max: 0 },
  states: {},
  longestClosureMs: 0,
  phoneMs: 0,
  onlineS: 0,
};

export type Trip = {
  id: number;
  startedAt: number;
  endedAt: number | null;
  demo: boolean;
  score: number | null;
  summary: TripSummary;
};

export type TripEventKind = 'alert' | 'state' | 'crash' | 'unresponsive' | 'sos' | 'connected' | 'disconnected';
export type TripEvent = { id: number; tripId: number; t: number; kind: TripEventKind; value: string; detail: string | null };

export type HrPoint = { t: number; bpm: number };

export type IncidentOutcome = 'pending' | 'cancelled' | 'sent' | 'failed';
export type Incident = {
  id: number;
  tripId: number | null;
  t: number;
  kind: 'crash' | 'manual' | 'unresponsive';
  gPeak: number | null;
  lat: number | null;
  lon: number | null;
  piId: string | null;
  outcome: IncidentOutcome;
  checks: CrashChecks | null;
  /** Phone |a| in g around the impact, ~20 Hz, for the timeline: [t_ms, g]. */
  motion: [number, number][];
  clipPath: string | null;
  smsSent: number;
  called: string | null;
};
