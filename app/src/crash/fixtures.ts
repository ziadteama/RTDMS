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
