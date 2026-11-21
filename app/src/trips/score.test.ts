import { EMPTY_SUMMARY, type TripSummary } from './model';
import { safetyScore, weekStart, weeklyTrend } from './score';

const hour = (patch: Partial<TripSummary> = {}): TripSummary => ({ ...EMPTY_SUMMARY, onlineS: 3600, ...patch });

describe('safetyScore', () => {
  it('is 100 for a clean hour and null for a trip too short to judge', () => {
    expect(safetyScore(hour())).toBe(100);
    expect(safetyScore({ ...EMPTY_SUMMARY, onlineS: 10 })).toBeNull();
  });

  it('matches the documented examples', () => {
    expect(safetyScore(hour({ alerts: { short_beep: 0, repeated: 2, continuous: 1, max: 0 } }))).toBe(78);
    expect(safetyScore(hour({ alerts: { short_beep: 0, repeated: 0, continuous: 0, max: 5 } }))).toBe(37);
  });

  it('falls as alerts get more severe and as phone time grows', () => {
    const beep = safetyScore(hour({ alerts: { short_beep: 1, repeated: 0, continuous: 0, max: 0 } }))!;
    const max = safetyScore(hour({ alerts: { short_beep: 0, repeated: 0, continuous: 0, max: 1 } }))!;
    expect(max).toBeLessThan(beep);
    expect(safetyScore(hour({ phoneMs: 120_000 }))!).toBeLessThan(100);
  });

  it('does not let one beep in a two-minute trip sink the score', () => {
    expect(safetyScore({ ...EMPTY_SUMMARY, onlineS: 120, alerts: { short_beep: 1, repeated: 0, continuous: 0, max: 0 } })).toBe(86);
  });
});

describe('weeklyTrend', () => {
  it('averages scored trips per week, oldest first', () => {
    const now = new Date(2026, 10, 20, 12).getTime(); // Friday
    const thisWeek = weekStart(now);
    const lastWeek = thisWeek - 7 * 86400_000;
    const trend = weeklyTrend(
      [
        { startedAt: thisWeek + 3600_000, score: 80 },
        { startedAt: thisWeek + 7200_000, score: 90 },
        { startedAt: lastWeek + 3600_000, score: 60 },
        { startedAt: lastWeek + 7200_000, score: null },
      ],
      now,
      3,
    );
    expect(trend.map((w) => w.score)).toEqual([null, 60, 85]);
    expect(trend[2]!.trips).toBe(2);
    expect(new Date(trend[2]!.week).getDay()).toBe(1); // Monday
  });
});
