import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import {
  CrashMonitor,
  DEFAULT_CRASH_CONFIG,
  G,
  detectCrash,
  magnitudeG,
  synthesizeCrash,
  unpackMotion,
  type MotionSample,
  type SpeedSample,
} from './detector';
import {
  droppedPhoneMovingThenPickedUp,
  droppedPhoneStationary,
  injectCrash,
  normalDrive,
  rollerCoasterSpikes,
  speedBump,
} from './fixtures';

const T0 = 1_700_000_000_000;

function still(t0: number, ms: number, hz = 100): MotionSample[] {
  const out: MotionSample[] = [];
  for (let t = t0; t < t0 + ms; t += 1000 / hz) out.push({ t, ax: 0, ay: 0, az: G, gx: 0, gy: 0, gz: 0 });
  return out;
}

function spikeAt(samples: MotionSample[], t: number, g: number): MotionSample[] {
  return samples.map((s) => (Math.abs(s.t - t) < 5 ? { ...s, ax: g * G, az: 0 } : s));
}

function speeds(t0: number, ms: number, kmhAt: (t: number) => number | null): SpeedSample[] {
  const out: SpeedSample[] = [];
  for (let t = t0; t <= t0 + ms; t += 1000) out.push({ t, kmh: kmhAt(t) });
  return out;
}

describe('detectCrash', () => {
  const impact = T0 + 10_000;
  const motion = spikeAt(still(T0, 20_000), impact, 6);

  it('spike + speed drop to 0 → event', () => {
    const gps = speeds(T0, 20_000, (t) => (t <= impact ? 60 : 0));
    const e = detectCrash(motion, gps);
    expect(e).not.toBeNull();
    expect(e!.tImpact).toBe(impact);
    expect(e!.gPeak).toBeCloseTo(6, 1);
    expect(e!.speedBeforeKmh).toBe(60);
    expect(e!.tStopped).toBe(impact + 1000);
  });

  it('spike without a speed drop → none (pothole, phone knocked in its mount)', () => {
    const gps = speeds(T0, 20_000, () => 60);
    expect(detectCrash(motion, gps)).toBeNull();
  });

  it('below 20 km/h → none (not armed: parking, phone dropped while walking)', () => {
    const gps = speeds(T0, 20_000, (t) => (t <= impact ? 15 : 0));
    expect(detectCrash(motion, gps)).toBeNull();
  });

  it('spike below 4 g → none, even with a stop (hard braking at a light)', () => {
    const soft = spikeAt(still(T0, 20_000), impact, 3.2);
    const gps = speeds(T0, 20_000, (t) => (t <= impact ? 60 : 0));
    expect(detectCrash(soft, gps)).toBeNull();
  });

  it('stop later than 5 s after the spike → none', () => {
    const gps = speeds(T0, 20_000, (t) => (t <= impact + 6000 ? 60 : 0));
    expect(detectCrash(motion, gps)).toBeNull();
  });

  it('stop that does not hold (drives on) → none', () => {
    const gps = speeds(T0, 20_000, (t) => (t <= impact ? 60 : t <= impact + 2000 ? 0 : 30));
    expect(detectCrash(motion, gps)).toBeNull();
  });

  it('waits for enough GPS after the stop before deciding', () => {
    const gps = speeds(T0, 12_000, (t) => (t <= impact ? 60 : 0)); // only 2 s after the stop
    expect(detectCrash(motion, gps)).toBeNull();
    const more = speeds(T0, 15_000, (t) => (t <= impact ? 60 : 0));
    expect(detectCrash(motion, more)).not.toBeNull();
  });

  it('GPS without speed (null) never arms or confirms', () => {
    const gps = speeds(T0, 20_000, () => null);
    expect(detectCrash(motion, gps)).toBeNull();
  });

  it('reports optional checks and leaves unavailable ones null', () => {
    const c = synthesizeCrash(T0, 7, 55);
    const e = detectCrash(c.samples, c.speeds, DEFAULT_CRASH_CONFIG, {
      faceLost: [c.tImpact + 400],
      hr: [
        { t: c.tImpact - 10_000, bpm: 72 },
        { t: c.tImpact + 8_000, bpm: 118 },
      ],
    });
    expect(e).not.toBeNull();
    expect(e!.checks).toEqual({ flipped: true, faceLost: true, headJerk: null, hrSpike: true });
  });
});

describe('CrashMonitor (streaming)', () => {
  it('reports one event per impact as batches arrive', () => {
    const c = synthesizeCrash(T0, 6, 50);
    const m = new CrashMonitor();
    const events = [];
    for (let t = T0; t <= T0 + 14_000; t += 200) {
      m.addMotion(c.samples.filter((s) => s.t >= t - 200 && s.t < t));
      for (const s of c.speeds.filter((s) => s.t >= t - 200 && s.t < t)) m.addSpeed(s);
      const e = m.check(t);
      if (e) events.push(e);
    }
    expect(events).toHaveLength(1);
    expect(events[0]!.tImpact - c.tImpact).toBeGreaterThanOrEqual(0);
    expect(events[0]!.tImpact - c.tImpact).toBeLessThan(120); // peak of the 120 ms pulse
  });

  it('unpacks the native flat batch', () => {
    const s = unpackMotion([1, 0, 0, G, 0, 0, 0, 2, 1, 2, 3, 4, 5, 6]);
    expect(s).toHaveLength(2);
    expect(magnitudeG(s[0]!)).toBeCloseTo(1);
    expect(s[1]).toEqual({ t: 2, ax: 1, ay: 2, az: 3, gx: 4, gy: 5, gz: 6 });
  });
});

describe('replay: hardening cases (dropped phone, speed bump, roller-coaster, missing GPS)', () => {
  it('dropped phone while stationary (no prior speed) → no event', () => {
    const { samples, speeds } = droppedPhoneStationary(T0, 6);
    expect(detectCrash(samples, speeds)).toBeNull();
  });

  it('dropped phone while driving then picked up and moved → no event (no stillness)', () => {
    const { samples, speeds } = droppedPhoneMovingThenPickedUp(T0, 40, 6);
    expect(detectCrash(samples, speeds)).toBeNull();
  });

  it('speed bump at 30 km/h (3.5–4.5 g spike then continued motion) → no event', () => {
    const { samples, speeds } = speedBump(T0, 30, 4.0);
    expect(detectCrash(samples, speeds)).toBeNull();
  });

  it('roller-coaster-like repeated 4–5 g spikes with sustained motion → no event', () => {
    const { samples, speeds } = rollerCoasterSpikes(T0, 60);
    expect(detectCrash(samples, speeds)).toBeNull();
  });

  it('real-crash positive still passes detection', () => {
    const c = synthesizeCrash(T0, 6.5, 50);
    const e = detectCrash(c.samples, c.speeds);
    expect(e).not.toBeNull();
    expect(e!.tImpact - c.tImpact).toBeLessThan(120); // peak of the 120 ms half-sine pulse
    expect(e!.gPeak).toBeGreaterThan(6);
    expect(e!.speedBeforeKmh).toBe(50);
  });

  /**
   * Phone-only crash detection intentionally requires prior GPS speed (> 20 km/h) to arm
   * and GPS speed drop (<= 5 km/h) to confirm. Even when IMU indicates post-impact stillness,
   * missing GPS data means the detector cannot distinguish between a vehicle collision and a
   * phone dropped on a floor while stationary. Therefore, it refuses to trigger automatically.
   * Manual SOS remains available to the driver.
   */
  it('crash where GPS is missing but IMU shows stillness → no event (requires speed gating & confirmation)', () => {
    const c = synthesizeCrash(T0, 6.5, 50);
    expect(detectCrash(c.samples, [])).toBeNull();
    const nullGps: SpeedSample[] = c.speeds.map((s) => ({ t: s.t, kmh: null }));
    expect(detectCrash(c.samples, nullGps)).toBeNull();
  });
});

describe('replay: normal driving with an injected crash', () => {
  const drive = normalDrive(T0, 20, 100, 11);

  it('the 20-minute normal drive alone produces no event (bumps, hard braking, stops)', () => {
    expect(Math.max(...drive.samples.map(magnitudeG))).toBeGreaterThan(1.5); // bumps are in there
    expect(Math.min(...drive.speeds.map((s) => s.kmh ?? 99))).toBe(0); // real stops are in there
    expect(detectCrash(drive.samples, drive.speeds)).toBeNull();
  });

  it.each([5, 6, 7, 8])('detects an injected %i g impact at speed', (g) => {
    // pick an impact time where the car is moving above 20 km/h
    const moving = drive.speeds.filter((s) => (s.kmh ?? 0) > 35);
    const tImpact = moving[Math.floor(moving.length / 2)]!.t + 300;
    const crashed = injectCrash(drive, tImpact, g);
    const window = crashed.samples.filter((s) => s.t > tImpact - 15_000 && s.t < tImpact + 10_000);
    const gps = crashed.speeds.filter((s) => s.t > tImpact - 15_000 && s.t < tImpact + 10_000);
    const e = detectCrash(window, gps);
    expect(e).not.toBeNull();
    expect(Math.abs(e!.tImpact - tImpact)).toBeLessThan(100);
    expect(e!.checks.flipped).toBe(true);
  });
});

/**
 * Real recordings (opt-in): driverBehaviorDataset (Ferreira et al., PLOS ONE 2017), a mounted
 * phone over ~51 min of driving incl. aggressive braking / turns. Not committed (no license in the
 * source repo): `npm run fetch:driving-data` clones it to .data/. GPS is not in the dataset, so
 * the worst case is assumed: armed throughout and a stop after every candidate spike.
 */
const DATA = process.env.DRIVING_DATA_DIR ?? join(__dirname, '../../.data/driverBehaviorDataset/data');
const real = existsSync(DATA) ? describe : describe.skip;

real('replay: real recorded driving (driverBehaviorDataset)', () => {
  const trips = ['16', '17', '20', '21'];
  const load = (trip: string): MotionSample[] =>
    readFileSync(join(DATA, trip, 'acelerometro_terra.csv'), 'utf8')
      .trim()
      .split('\n')
      .slice(1)
      .map((line) => {
        const [, ns, x, y, z] = line.split(',');
        return { t: Number(ns) / 1e6, ax: Number(x), ay: Number(y), az: Number(z), gx: 0, gy: 0, gz: 0 };
      });

  it.each(trips)('trip %s: no false alarm even when armed and stopped (worst case)', (trip) => {
    const samples = load(trip);
    const t0 = samples[0]!.t;
    const t1 = samples[samples.length - 1]!.t;
    // worst case GPS: 50 km/h, then a stop 1 s after every sample → only the g threshold decides
    const gps: SpeedSample[] = [];
    for (let t = t0; t <= t1 + 10_000; t += 1000) gps.push({ t, kmh: 50 });
    const stopEverywhere = (from: number): SpeedSample[] => [
      ...gps.filter((s) => s.t <= from),
      ...gps.filter((s) => s.t > from).map((s) => ({ ...s, kmh: 0 })),
    ];
    const peak = samples.reduce((a, s) => (magnitudeG(s) > magnitudeG(a) ? s : a));
    expect(detectCrash(samples, stopEverywhere(peak.t))).toBeNull();
  });

  it.each([5, 6, 7, 8])('trip 16 with an injected %i g impact → detected', (g) => {
    const samples = load('16');
    const tImpact = samples[Math.floor(samples.length / 2)]!.t;
    const gps: SpeedSample[] = [];
    for (let t = samples[0]!.t; t <= samples[samples.length - 1]!.t; t += 1000)
      gps.push({ t, kmh: t <= tImpact ? 50 : 0 });
    const crashed = injectCrash({ samples, speeds: gps }, tImpact, g);
    const e = detectCrash(
      crashed.samples.filter((s) => s.t > tImpact - 15_000 && s.t < tImpact + 10_000),
      crashed.speeds,
    );
    expect(e).not.toBeNull();
  });
});
