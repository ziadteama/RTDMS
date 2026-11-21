import { armState, gpsLost, GPS_STALE_MS, MOTION_STALE_MS } from './arm-state';
import { DEFAULT_CRASH_CONFIG, type SpeedSample } from './detector';

describe('armState', () => {
  const now = 1_700_000_100_000;
  const recentMovingSpeeds: SpeedSample[] = [
    { t: now - 5_000, kmh: 35 },
    { t: now - 1_000, kmh: 28 },
  ];

  it('arms when enabled, not paused, GPS and motion are fresh, and recent speed > 20 km/h', () => {
    const res = armState({
      enabled: true,
      paused: false,
      now,
      gpsAt: now - 500,
      motionAt: now - 100,
      speeds: recentMovingSpeeds,
    });
    expect(res).toEqual({ armed: true, reason: 'armed' });
  });

  it('disarms with "disabled" when crashDetection is off', () => {
    const res = armState({
      enabled: false,
      paused: false,
      now,
      gpsAt: now,
      motionAt: now,
      speeds: recentMovingSpeeds,
    });
    expect(res).toEqual({ armed: false, reason: 'disabled' });
  });

  it('disarms with "disabled" when monitoring is paused', () => {
    const res = armState({
      enabled: true,
      paused: true,
      now,
      gpsAt: now,
      motionAt: now,
      speeds: recentMovingSpeeds,
    });
    expect(res).toEqual({ armed: false, reason: 'disabled' });
  });

  it('disarms with "no_gps" when gpsAt is null or stale', () => {
    expect(
      armState({
        enabled: true,
        paused: false,
        now,
        gpsAt: null,
        motionAt: now,
        speeds: recentMovingSpeeds,
      }),
    ).toEqual({ armed: false, reason: 'no_gps' });

    expect(
      armState({
        enabled: true,
        paused: false,
        now,
        gpsAt: now - (GPS_STALE_MS + 1),
        motionAt: now,
        speeds: recentMovingSpeeds,
      }),
    ).toEqual({ armed: false, reason: 'no_gps' });
  });

  it('disarms with "no_motion" when motionAt is null or stale', () => {
    expect(
      armState({
        enabled: true,
        paused: false,
        now,
        gpsAt: now,
        motionAt: null,
        speeds: recentMovingSpeeds,
      }),
    ).toEqual({ armed: false, reason: 'no_motion' });

    expect(
      armState({
        enabled: true,
        paused: false,
        now,
        gpsAt: now,
        motionAt: now - (MOTION_STALE_MS + 1),
        speeds: recentMovingSpeeds,
      }),
    ).toEqual({ armed: false, reason: 'no_motion' });
  });

  it('disarms with "too_slow" when no recent speed exceeds threshold in arm window', () => {
    const slowSpeeds: SpeedSample[] = [
      { t: now - 2_000, kmh: 15 },
      { t: now - 500, kmh: 18 },
    ];
    expect(
      armState({
        enabled: true,
        paused: false,
        now,
        gpsAt: now,
        motionAt: now,
        speeds: slowSpeeds,
      }),
    ).toEqual({ armed: false, reason: 'too_slow' });

    // Speed was fast enough, but too long ago (> armWindowMs)
    const expiredSpeeds: SpeedSample[] = [
      { t: now - (DEFAULT_CRASH_CONFIG.armWindowMs + 100), kmh: 50 },
    ];
    expect(
      armState({
        enabled: true,
        paused: false,
        now,
        gpsAt: now,
        motionAt: now,
        speeds: expiredSpeeds,
      }),
    ).toEqual({ armed: false, reason: 'too_slow' });

    // Speeds with null kmh do not count
    expect(
      armState({
        enabled: true,
        paused: false,
        now,
        gpsAt: now,
        motionAt: now,
        speeds: [{ t: now - 1_000, kmh: null }],
      }),
    ).toEqual({ armed: false, reason: 'too_slow' });
  });

  it('evaluates reason precedence: disabled > no_gps > no_motion > too_slow', () => {
    // Disabled takes precedence over missing GPS and missing motion
    expect(
      armState({
        enabled: false,
        paused: false,
        now,
        gpsAt: null,
        motionAt: null,
        speeds: [],
      }),
    ).toEqual({ armed: false, reason: 'disabled' });

    // Missing GPS takes precedence over missing motion
    expect(
      armState({
        enabled: true,
        paused: false,
        now,
        gpsAt: null,
        motionAt: null,
        speeds: [],
      }),
    ).toEqual({ armed: false, reason: 'no_gps' });

    // Missing motion takes precedence over too_slow
    expect(
      armState({
        enabled: true,
        paused: false,
        now,
        gpsAt: now,
        motionAt: null,
        speeds: [],
      }),
    ).toEqual({ armed: false, reason: 'no_motion' });
  });

  it('gpsLost helper checks staleness boundary', () => {
    expect(gpsLost(null, now)).toBe(true);
    expect(gpsLost(now - GPS_STALE_MS, now)).toBe(false);
    expect(gpsLost(now - (GPS_STALE_MS + 1), now)).toBe(true);
  });
});
