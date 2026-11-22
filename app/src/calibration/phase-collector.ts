import { mad, median, openStateNoise } from './stats';
import type { EarSample, PhaseResult, RejectCounts } from './types';

export class PhaseCollector {
  readonly settleS: number;
  private readonly ear: number[] = [];
  private readonly yaw: number[] = [];
  private readonly pitch: number[] = [];
  private readonly luma: number[] = [];
  private readonly rejects: RejectCounts = {
    noFace: 0,
    headTurned: 0,
    invalidEar: 0,
    total: 0,
  };

  constructor(settleS = 2.0) {
    this.settleS = settleS;
  }

  /**
   * Push a sample. Timestamps sample.t are relative to phase start.
   * Discards the first settleS seconds (default 2 s).
   * Samples with earValid=false or ear=null are not counted, but recorded as rejects.
   */
  push(sample: EarSample): boolean {
    const tSec = sample.t > 100 ? sample.t / 1000 : sample.t;
    if (tSec < this.settleS) {
      return false;
    }

    this.luma.push(sample.luma);

    if (!sample.faceFound) {
      this.rejects.noFace += 1;
      this.rejects.total += 1;
      return false;
    }

    if (
      (sample.yaw !== null && Math.abs(sample.yaw) > 15) ||
      (sample.pitch !== null && Math.abs(sample.pitch) > 15)
    ) {
      this.rejects.headTurned += 1;
      this.rejects.total += 1;
      return false;
    }

    if (!sample.earValid || sample.ear === null) {
      this.rejects.invalidEar += 1;
      this.rejects.total += 1;
      return false;
    }

    this.ear.push(sample.ear);
    if (sample.yaw !== null) this.yaw.push(sample.yaw);
    if (sample.pitch !== null) this.pitch.push(sample.pitch);
    return true;
  }

  pushEar(ear: number, t = 2.5): boolean {
    return this.push({
      t,
      ear,
      earValid: true,
      faceFound: true,
      yaw: 0,
      pitch: 0,
      luma: 50,
      faceBoxFraction: 0.5,
    });
  }

  get samplesCount(): number {
    return this.ear.length;
  }

  get rejectCount(): number {
    return this.rejects.total;
  }

  get rejectBreakdown(): RejectCounts {
    return { ...this.rejects };
  }

  result(): PhaseResult {
    const meanLuma =
      this.luma.length > 0
        ? this.luma.reduce((sum, v) => sum + v, 0) / this.luma.length
        : null;

    return {
      ear: median(this.ear),
      yaw: median(this.yaw),
      pitch: median(this.pitch),
      meanLuma,
      n: this.ear.length,
      noise: openStateNoise(this.ear),
      mad: mad(this.ear),
      rejects: { ...this.rejects },
      totalSamples: this.ear.length + this.rejects.total,
    };
  }
}
