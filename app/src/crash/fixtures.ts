/**
 * Test fixtures for the crash detector. Synthetic, deterministic, and shaped after real phone
 * recordings (driverBehaviorDataset, see app/docs/EVIDENCE.md: mounted phone, 51 Hz, aggressive
 * braking / cornering peak 1.4–2.5 g with gravity). Not used by the app at runtime.
 */
import { rngFor as rng } from '@/demo/rng';

import { G, type MotionSample, type SpeedSample } from './detector';

/**
 * `minutes` of city driving at `hz`: road vibration, speed bumps (up to 2.5 g), hard braking
 * (0.8 g for 2 s), and full stops at lights where the speed really drops to 0 and stays there.
 * GPS speed at 1 Hz.
 */
export function normalDrive(t0: number, minutes: number, hz = 100, seed = 7) {
  const r = rng(seed);
  const samples: MotionSample[] = [];
  const speeds: SpeedSample[] = [];
  const end = t0 + minutes * 60_000;
  const step = 1000 / hz;
  // A speed profile: cruise segments separated by stops at lights.
  const profile: { until: number; kmh: number }[] = [];
  for (let t = t0; t < end; ) {
    const cruise = 40_000 + r() * 60_000;
    profile.push({ until: t + cruise, kmh: 30 + r() * 45 });
    t += cruise;
    profile.push({ until: t + 15_000 + r() * 20_000, kmh: 0 });
    t = profile[profile.length - 1]!.until;
  }
  const targetAt = (t: number) => profile.find((p) => t < p.until)?.kmh ?? 0;
  let v = 0;
  let nextBump = t0 + 20_000 * r();
  let bump = { t: -1, g: 0 };
  let brakeUntil = -1;
  for (let t = t0; t < end; t += step) {
    const target = targetAt(t);
    const hard = target === 0 && v > 25 && r() < 0.002 && brakeUntil < t;
    if (hard) brakeUntil = t + 2000;
    const decel = brakeUntil > t ? 0.8 : 0.25; // g
    const dv = (target - v) * 0.002 * step;
    const maxDv = decel * G * 3.6 * (step / 1000);
    v = Math.max(0, v + Math.max(-maxDv, Math.min(maxDv * 0.6, dv)));
    const longitudinal = target < v ? -Math.min(decel, ((v - target) / 3.6 / 3) / G) : 0.05;
    if (t >= nextBump && v > 15) {
      bump = { t, g: 0.8 + r() * 1.5 }; // vertical excursion on top of 1 g → total up to ~2.5 g
      nextBump = t + 30_000 + r() * 90_000;
    }
    const dtb = t - bump.t;
    const bumpG = dtb >= 0 && dtb < 150 ? bump.g * Math.sin((Math.PI * dtb) / 150) : 0;
    const vib = v > 0 ? 0.04 + v / 1500 : 0.01;
    samples.push({
      t,
      ax: (r() - 0.5) * vib * G,
      ay: longitudinal * G + (r() - 0.5) * vib * G,
      az: G * (1 + bumpG) + (r() - 0.5) * vib * G,
      gx: (r() - 0.5) * 0.05,
      gy: (r() - 0.5) * 0.05,
      gz: (r() - 0.5) * 0.08,
    });
    if (Math.round(t - t0) % 1000 < step) speeds.push({ t, kmh: Math.round(v * 10) / 10 });
  }
  return { samples, speeds };
}

/** Add a crash at `tImpact`: a `gPeak` pulse, phone thrown onto its side, speed to 0. */
export function injectCrash(
  drive: { samples: MotionSample[]; speeds: SpeedSample[] },
  tImpact: number,
  gPeak: number,
) {
  const samples = drive.samples.map((s) => {
    const dt = s.t - tImpact;
    if (dt < 0) return s;
    if (dt < 100) {
      const k = Math.sin((Math.PI * dt) / 100);
      return { ...s, ay: s.ay - gPeak * G * k * 0.9, az: s.az + gPeak * G * k * 0.4 };
    }
    return { ...s, ax: G, ay: 0.1, az: 0.2, gx: 0, gy: 0, gz: 0 };
  });
  const speeds = drive.speeds.map((s) =>
    s.t <= tImpact ? s : { ...s, kmh: s.t <= tImpact + 1000 ? 12 : 0 },
  );
  return { samples, speeds };
}

/** Stationary drop: stationary phone drops onto a surface, impact spike, then sits still. */
export function droppedPhoneStationary(t0: number, gPeak = 6) {
  const tImpact = t0 + 5_000;
  const samples: MotionSample[] = [];
  const speeds: SpeedSample[] = [];
  for (let t = t0; t < tImpact + 8_000; t += 10) {
    const dt = t - tImpact;
    let az = G;
    let ax = 0;
    if (dt >= 0 && dt < 100) {
      const k = Math.sin((Math.PI * dt) / 100);
      az += gPeak * G * k;
      ax += (gPeak / 2) * G * k;
    }
    samples.push({ t, ax, ay: 0, az, gx: 0, gy: 0, gz: 0 });
  }
  for (let t = t0; t <= tImpact + 8_000; t += 1_000) speeds.push({ t, kmh: 0 });
  return { samples, speeds, tImpact };
}

/** Driving drop then picked up: dropped at speed, stops, but phone is picked up/handled. */
export function droppedPhoneMovingThenPickedUp(t0: number, speedKmh = 40, gPeak = 6) {
  const tImpact = t0 + 5_000;
  const samples: MotionSample[] = [];
  const speeds: SpeedSample[] = [];
  for (let t = t0; t < tImpact + 8_000; t += 10) {
    const dt = t - tImpact;
    let ax = 0;
    let ay = 0;
    let az = G;
    let gx = 0;
    let gy = 0;
    let gz = 0;
    if (dt >= 0 && dt < 100) {
      const k = Math.sin((Math.PI * dt) / 100);
      ax += gPeak * G * k;
    } else if (dt >= 100) {
      // Driver picks up and moves the phone (continuous high gyro and accel variance)
      ax = 0.6 * G * Math.sin(t / 80);
      ay = 0.5 * G * Math.cos(t / 90);
      az = G + 0.4 * G * Math.sin(t / 110);
      gx = 0.8 * Math.sin(t / 100);
      gy = 0.6 * Math.cos(t / 100);
      gz = 0.9 * Math.sin(t / 120);
    }
    samples.push({ t, ax, ay, az, gx, gy, gz });
  }
  for (let t = t0; t <= tImpact + 8_000; t += 1_000)
    speeds.push({ t, kmh: t <= tImpact ? speedKmh : 0 });
  return { samples, speeds, tImpact };
}

/** Speed bump: 3.5–4.5 g spike at ~30 km/h, car continues moving with normal road vibration. */
export function speedBump(t0: number, speedKmh = 30, gPeak = 4.0) {
  const tBump = t0 + 5_000;
  const samples: MotionSample[] = [];
  const speeds: SpeedSample[] = [];
  for (let t = t0; t < tBump + 8_000; t += 10) {
    const dt = t - tBump;
    const bumpG = dt >= 0 && dt < 150 ? (gPeak - 1) * Math.sin((Math.PI * dt) / 150) : 0;
    samples.push({
      t,
      ax: 0.1 * Math.sin(t / 50),
      ay: 0.1 * Math.cos(t / 60),
      az: G * (1 + bumpG) + 0.1 * Math.sin(t / 40),
      gx: 0.02,
      gy: 0.02,
      gz: 0.03,
    });
  }
  for (let t = t0; t <= tBump + 8_000; t += 1_000) speeds.push({ t, kmh: speedKmh });
  return { samples, speeds, tBump };
}

/** Roller-coaster: repeated 4–5 g spikes with sustained high-intensity motion. */
export function rollerCoasterSpikes(t0: number, speedKmh = 60) {
  const samples: MotionSample[] = [];
  const speeds: SpeedSample[] = [];
  const spikes = [t0 + 2_000, t0 + 4_000, t0 + 6_000];
  for (let t = t0; t < t0 + 10_000; t += 10) {
    let extraG = 0;
    for (const ts of spikes) {
      const dt = t - ts;
      if (dt >= 0 && dt < 120) extraG += 3.8 * Math.sin((Math.PI * dt) / 120);
    }
    samples.push({
      t,
      ax: 1.5 * G * Math.sin(t / 70),
      ay: 1.2 * G * Math.cos(t / 80),
      az: G + extraG * G + 0.5 * G * Math.sin(t / 90),
      gx: 1.2 * Math.sin(t / 100),
      gy: 0.8 * Math.cos(t / 110),
      gz: 1.5 * Math.sin(t / 90),
    });
  }
  for (let t = t0; t <= t0 + 10_000; t += 1_000) speeds.push({ t, kmh: speedKmh });
  return { samples, speeds };
}
