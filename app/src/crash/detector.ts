import { postImpactStillness } from './stillness';

/**
 * Phone-side crash detection: pure functions, no React Native imports, unit-tested in Node.
 *
 *   detectCrash(samples, speeds, config, extras?) → CrashEvent | null
 *
 * 1. Armed: GPS speed above `armSpeedKmh` some time in the `armWindowMs` before the impact.
 *    Phone sensors operate independently of the Pi.
 * 2. Impact: accelerometer magnitude above `impactG`.
 * 3. Confirm: GPS speed at or below `stopSpeedKmh` within `confirmWithinMs` after the impact, and
 *    still there `holdMs` later. No decision until that much GPS data has arrived.
 *    IMU stillness for 3 s within 6 s is also required.
 * 4. Optional checks are reported, never required (they would only delay help):
 *    phone flipped (gravity direction turned), Pi lost the face / saw a head jerk, HR spike.
 */

export type MotionSample = {
  /** Wall-clock ms. */
  t: number;
  /** m/s², gravity included (Android TYPE_ACCELEROMETER). */
  ax: number;
  ay: number;
  az: number;
  /** rad/s. */
  gx: number;
  gy: number;
  gz: number;
};

/** GPS speed; null when the fix has no speed. */
export type SpeedSample = { t: number; kmh: number | null };

export type CrashConfig = {
  armSpeedKmh: number;
  armWindowMs: number;
  impactG: number;
  stopSpeedKmh: number;
  confirmWithinMs: number;
  holdMs: number;
  stillWithinMs: number;
  stillHoldMs: number;
  stillAccelToleranceG: number;
  stillGyroRadS: number;
  motionMaxGapMs: number;
  flipDeg: number;
  hrSpikeBpm: number;
};

export const DEFAULT_CRASH_CONFIG: CrashConfig = {
  armSpeedKmh: 20,
  armWindowMs: 10_000,
  impactG: 4,
  stopSpeedKmh: 5,
  confirmWithinMs: 5_000,
  holdMs: 3_000,
  stillWithinMs: 6_000,
  stillHoldMs: 3_000,
  stillAccelToleranceG: 0.25,
  stillGyroRadS: 0.15,
  motionMaxGapMs: 100,
  flipDeg: 60,
  hrSpikeBpm: 25,
};

/** Optional evidence from the Pi, by time (ms). Absent arrays mean "not available". */
export type CrashExtras = {
  /** Times the Pi reported face: false. */
  faceLost?: number[];
  /** Times the Pi reported a sudden head movement (not in stream.py yet). */
  headJerk?: number[];
  /** Watch heart rate samples. */
  hr?: { t: number; bpm: number }[];
};

export type CrashChecks = {
  flipped: boolean | null;
  faceLost: boolean | null;
  headJerk: boolean | null;
  hrSpike: boolean | null;
};

export type CrashEvent = {
  tImpact: number;
  gPeak: number;
  speedBeforeKmh: number;
  tStopped: number;
  checks: CrashChecks;
};

export const G = 9.80665;

export const magnitudeG = (s: MotionSample): number => Math.hypot(s.ax, s.ay, s.az) / G;

function meanVector(samples: MotionSample[], from: number, to: number): [number, number, number] | null {
  let x = 0;
  let y = 0;
  let z = 0;
  let n = 0;
  for (const s of samples)
    if (s.t >= from && s.t < to) {
      x += s.ax;
      y += s.ay;
      z += s.az;
      n++;
    }
  return n ? [x / n, y / n, z / n] : null;
}

function angleDeg(a: [number, number, number], b: [number, number, number]): number {
  const dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const na = Math.hypot(...a);
  const nb = Math.hypot(...b);
  if (!na || !nb) return 0;
  return (Math.acos(Math.max(-1, Math.min(1, dot / (na * nb)))) * 180) / Math.PI;
}

function anyWithin(ts: number[] | undefined, from: number, to: number): boolean | null {
  if (!ts) return null;
  return ts.some((t) => t >= from && t <= to);
}

/**
 * Find the strongest impact in `samples` that passes arming and confirmation.
 * `samples` and `speeds` must be sorted by time.
 */
export function detectCrash(
  samples: MotionSample[],
  speeds: SpeedSample[],
  config: CrashConfig = DEFAULT_CRASH_CONFIG,
  extras: CrashExtras = {},
): CrashEvent | null {
  // Candidate impacts: local peaks above the threshold, strongest first.
  const peaks: { t: number; g: number }[] = [];
  for (let i = 0; i < samples.length; i++) {
    const g = magnitudeG(samples[i]!);
    if (g < config.impactG) continue;
    const prev = i > 0 ? magnitudeG(samples[i - 1]!) : 0;
    const next = i + 1 < samples.length ? magnitudeG(samples[i + 1]!) : 0;
    if (g >= prev && g >= next) peaks.push({ t: samples[i]!.t, g });
  }
  peaks.sort((a, b) => b.g - a.g);

  const valid = speeds.filter((s): s is { t: number; kmh: number } => s.kmh !== null);
  const lastSpeedT = valid.length ? valid[valid.length - 1]!.t : -Infinity;

  for (const peak of peaks) {
    const before = valid.filter((s) => s.t >= peak.t - config.armWindowMs && s.t <= peak.t);
    const speedBefore = before.reduce((m, s) => Math.max(m, s.kmh), 0);
    if (speedBefore <= config.armSpeedKmh) continue; // not armed: parked, walking, phone dropped

    const stop = valid.find(
      (s) => s.t > peak.t && s.t <= peak.t + config.confirmWithinMs && s.kmh <= config.stopSpeedKmh,
    );
    if (!stop) continue;
    if (lastSpeedT < stop.t + config.holdMs) continue; // not enough GPS after the stop yet
    const stays = valid
      .filter((s) => s.t >= stop.t && s.t <= stop.t + config.holdMs)
      .every((s) => s.kmh <= config.stopSpeedKmh);
    if (!postImpactStillness(samples, peak.t, config)) continue;
    if (!stays) continue; // hard braking at a light, then driving on


    return {
      tImpact: peak.t,
      gPeak: Math.round(peak.g * 100) / 100,
      speedBeforeKmh: Math.round(speedBefore),
      tStopped: stop.t,
      checks: optionalChecks(samples, peak.t, config, extras),
    };
  }
  return null;
}

function optionalChecks(samples: MotionSample[], impact: number, config: CrashConfig, extras: CrashExtras): CrashChecks {
    const pre = meanVector(samples, impact - 1500, impact - 200);
    const post = meanVector(samples, impact + 1000, impact + 3000);
    const flipped = pre && post ? angleDeg(pre, post) > config.flipDeg : null;

    let hrSpike: boolean | null = null;
    if (extras.hr) {
      const b = extras.hr.filter((h) => h.t >= impact - 30_000 && h.t < impact);
      const a = extras.hr.filter((h) => h.t > impact && h.t <= impact + 30_000);
      if (b.length && a.length) {
        const base = b.reduce((s, h) => s + h.bpm, 0) / b.length;
        hrSpike = Math.max(...a.map((h) => h.bpm)) - base >= config.hrSpikeBpm;
      }
    }

    return { flipped, faceLost: anyWithin(extras.faceLost, impact - 1000, impact + 3000),
      headJerk: anyWithin(extras.headJerk, impact - 1000, impact + 1000), hrSpike };
}

/**
 * Streaming wrapper: keeps the last few seconds of motion and GPS, runs `detectCrash` as data
 * arrives, reports each impact once.
 */
export class CrashMonitor {
  private samples: MotionSample[] = [];
  private speeds: SpeedSample[] = [];
  private lastEventT = -Infinity;
  private readonly keepMs: number;

  constructor(
    private readonly config: CrashConfig = DEFAULT_CRASH_CONFIG,
    private readonly refractoryMs = 60_000,
  ) {
    this.keepMs = config.armWindowMs + config.confirmWithinMs + config.holdMs + 2_000;
  }

  addMotion(batch: MotionSample[]): void {
    this.samples.push(...batch);
  }

  addSpeed(s: SpeedSample): void {
    this.speeds.push(s);
  }

  /** Run detection over the buffered window; returns a new event at most once per impact. */
  check(now: number, extras?: CrashExtras): CrashEvent | null {
    const cut = now - this.keepMs;
    if (this.samples.length && this.samples[0]!.t < cut) this.samples = this.samples.filter((s) => s.t >= cut);
    if (this.speeds.length && this.speeds[0]!.t < cut) this.speeds = this.speeds.filter((s) => s.t >= cut);
    const fresh = this.samples.filter((s) => s.t > this.lastEventT + this.refractoryMs);
    const e = detectCrash(fresh, this.speeds, this.config, extras);
    if (e) this.lastEventT = e.tImpact;
    return e;
  }

  /** Motion around an impact, kept with the incident for the sensor timeline. */
  window(from: number, to: number): MotionSample[] {
    return this.samples.filter((s) => s.t >= from && s.t <= to);
  }

  reset(): void {
    this.samples = [];
    this.speeds = [];
  }
}

/** Flattened native batch [t, ax, ay, az, gx, gy, gz]* → samples. */
export function unpackMotion(flat: number[]): MotionSample[] {
  const out: MotionSample[] = [];
  for (let i = 0; i + 6 < flat.length; i += 7)
    out.push({
      t: flat[i]!,
      ax: flat[i + 1]!,
      ay: flat[i + 2]!,
      az: flat[i + 3]!,
      gx: flat[i + 4]!,
      gy: flat[i + 5]!,
      gz: flat[i + 6]!,
    });
  return out;
}

/**
 * Synthetic crash for demo mode's "fake crash" button and the drop test: steady driving, a
 * `gPeak` impact, the phone ending on its side, GPS speed falling to 0. Same code path as a real one.
 */
export function synthesizeCrash(
  t0: number,
  gPeak = 6,
  speedKmh = 50,
): { samples: MotionSample[]; speeds: SpeedSample[]; tImpact: number } {
  const samples: MotionSample[] = [];
  const speeds: SpeedSample[] = [];
  const tImpact = t0 + 5_000;
  for (let t = t0; t < tImpact + 8_000; t += 10) {
    const dt = t - tImpact;
    const onSide = dt > 600;
    let ax = 0.3 * Math.sin(t / 37);
    let ay = onSide ? G : 0.2 * Math.sin(t / 53);
    let az = onSide ? 0.1 : G;
    if (dt >= 0 && dt < 120) {
      // ~120 ms impact pulse, half-sine
      const k = Math.sin((Math.PI * dt) / 120);
      ax += -gPeak * G * k * 0.8;
      az += gPeak * G * k * 0.6;
    }
    samples.push({ t, ax, ay, az, gx: onSide ? 0 : 0.02, gy: 0, gz: dt > 0 && dt < 600 ? 3 : 0 });
  }
  for (let t = t0; t <= tImpact + 8_000; t += 1_000)
    speeds.push({ t, kmh: t <= tImpact ? speedKmh : t <= tImpact + 2_000 ? 8 : 0 });
  return { samples, speeds, tImpact };
}
