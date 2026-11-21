/**
 * Demo history: eight weeks of example trips so the Trips tab and the weekly trend can be shown
 * without months of driving. Flagged demo=1, labelled "Demo" in the list, deleted when demo mode
 * is turned off.
 */
import { db } from '@/state/db';
import { EMPTY_SUMMARY, type TripSummary } from '@/trips/model';
import { safetyScore } from '@/trips/score';
import { rngFor } from './rng';

export function seedDemoHistory(now = Date.now()): void {
  if (db.listTrips().some((t) => t.demo)) return;
  const r = rngFor(42);
  for (let day = 55; day >= 1; day -= 1 + Math.floor(r() * 3)) {
    const start = new Date(now - day * 86400_000);
    start.setHours(7 + Math.floor(r() * 12), Math.floor(r() * 60), 0, 0);
    const minutes = 15 + Math.floor(r() * 75);
    const tired = start.getHours() >= 17 || r() < 0.2;
    const alerts = {
      short_beep: Math.floor(r() * 4),
      repeated: tired ? Math.floor(r() * 3) : 0,
      continuous: r() < 0.25 ? 1 : 0,
      max: tired && r() < 0.15 ? 1 : 0,
    };
    const summary: TripSummary = {
      ...EMPTY_SUMMARY,
      alerts,
      states: { distracted: alerts.short_beep, drowsy: alerts.repeated + alerts.max, phone: alerts.continuous },
      longestClosureMs: tired ? 1200 + Math.floor(r() * 1800) : 300 + Math.floor(r() * 500),
      phoneMs: alerts.continuous ? 8000 + Math.floor(r() * 20000) : 0,
      onlineS: minutes * 60,
    };
    const id = db.startTrip(start.getTime(), true);
    const t0 = start.getTime();
    let hr = 74 + r() * 6;
    for (let m = 0; m <= minutes; m += 0.5) {
      hr += (r() - 0.5) * 2 - (tired && m > minutes / 2 ? 0.08 : 0);
      db.addHr(id, t0 + m * 60_000, Math.round(hr));
    }
    db.addEvent(id, t0, 'connected', '');
    const add = (kind: 'alert' | 'state', value: string, n: number, detail: string | null) => {
      for (let i = 0; i < n; i++) db.addEvent(id, t0 + Math.floor(r() * minutes * 60_000), kind, value, detail);
    };
    add('state', 'distracted', alerts.short_beep, null);
    add('alert', 'short_beep', alerts.short_beep, 'face distracted');
    add('state', 'drowsy', alerts.repeated, null);
    add('alert', 'repeated', alerts.repeated, 'face drowsy');
    add('state', 'phone', alerts.continuous, null);
    add('alert', 'continuous', alerts.continuous, 'phone sustained');
    add('alert', 'max', alerts.max, 'face drowsy, physio confirms');
    db.saveTrip(id, { summary, score: safetyScore(summary), endedAt: t0 + minutes * 60_000 });
  }
}
