import { magnitudeG, type CrashConfig, type MotionSample } from './detector';

/** A continuous quiet interval, never bridging missing IMU samples. */
export function postImpactStillness(samples: MotionSample[], impact: number, config: CrashConfig): boolean {
  let start: number | null = null;
  let previous = -Infinity;
  for (const s of samples) {
    if (s.t <= impact) continue;
    if (s.t > impact + config.stillWithinMs) break;
    const quiet = Math.abs(magnitudeG(s) - 1) <= config.stillAccelToleranceG &&
      Math.hypot(s.gx, s.gy, s.gz) <= config.stillGyroRadS;
    if (!quiet) start = null;
    else {
      if (start === null || s.t - previous > config.motionMaxGapMs) start = s.t;
      if (s.t - start >= config.stillHoldMs) return true;
    }
    previous = s.t;
  }
  return false;
}
