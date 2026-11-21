import type { TripSummary } from './model';

/**
 * Safety score 0–100 from what fusion decided during the trip (alert onsets), not from raw model
 * scores. Penalty points per alert onset, normalized per hour driven (trips shorter than 10 min
 * count as 10 min so one beep in a 2-minute trip does not sink the score), plus phone-use time.
 *
 *   rate  = (Σ weight × onsets + phone seconds / 10) / max(hours, 1/6)
 *   score = round(100 × exp(−rate / 40))
 *
 * 0 points/h → 100. 10 points/h (e.g. 2 repeated + 1 continuous alarm in an hour) → 78.
 * 40 points/h → 37.
 */
export const WEIGHTS = { short_beep: 1, repeated: 3, continuous: 4, max: 8 } as const;

export function safetyScore(s: TripSummary): number | null {
  if (s.onlineS < 30) return null; // not enough driving to judge
  const points =
    (Object.keys(WEIGHTS) as (keyof typeof WEIGHTS)[]).reduce((sum, k) => sum + WEIGHTS[k] * s.alerts[k], 0) +
    s.phoneMs / 10_000;
  const hours = Math.max(s.onlineS / 3600, 1 / 6);
  return Math.round(100 * Math.exp(-points / hours / 40));
}

/** Monday 00:00 local time of the week containing `t`. */
export function weekStart(t: number): number {
  const d = new Date(t);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d.getTime();
}

/** Average score per week for the last `weeks` weeks (oldest first), null for weeks with no score. */
export function weeklyTrend(
  trips: { startedAt: number; score: number | null }[],
  now: number,
  weeks = 8,
): { week: number; score: number | null; trips: number }[] {
  const current = weekStart(now);
  const out = [];
  for (let i = weeks - 1; i >= 0; i--) {
    const d = new Date(current);
    d.setDate(d.getDate() - 7 * i);
    const week = d.getTime();
    const next = new Date(week);
    next.setDate(next.getDate() + 7);
    const scored = trips.filter((t) => t.startedAt >= week && t.startedAt < next.getTime() && t.score !== null);
    out.push({
      week,
      trips: scored.length,
      score: scored.length ? Math.round(scored.reduce((s, t) => s + t.score!, 0) / scored.length) : null,
    });
  }
  return out;
}
