import { toPhoneCalibrationPayload } from './payload';
import { PhaseCollector } from './phase-collector';
import { assessQuality } from './stats';
import type {
  BuildProfileResult,
  CalibrationQuality,
  PhaseResult,
  RejectCounts,
} from './types';

export const MIN_LUMA = 40;
export const MIN_SEPARATION = 0.04;
export const MIN_OPEN_SAMPLES = 10;
export const MIN_CLOSED_SAMPLES = 5;

export type PhaseInput =
  | PhaseCollector
  | PhaseResult
  | {
      ear: number | null;
      n?: number;
      noise?: number | null;
      mad?: number | null;
      meanLuma?: number | null;
      luma?: number | null;
      yaw?: number | null;
      pitch?: number | null;
      rejects?: Partial<RejectCounts>;
      totalSamples?: number;
    };

export type BuildProfileOptions = {
  minSeparation?: number;
  minOpenSamples?: number;
  minClosedSamples?: number;
  created?: number;
};

function toPhaseResult(input: PhaseInput, defaultMinN: number): PhaseResult {
  if (input instanceof PhaseCollector) {
    return input.result();
  }
  const ear = input.ear ?? null;
  const n = input.n ?? (ear !== null ? defaultMinN : 0);
  const meanLuma = input.meanLuma ?? (input as { luma?: number | null }).luma ?? 50;
  const rejects: RejectCounts = {
    noFace: input.rejects?.noFace ?? 0,
    headTurned: input.rejects?.headTurned ?? 0,
    invalidEar: input.rejects?.invalidEar ?? 0,
    total: input.rejects?.total ?? 0,
  };
  return {
    ear,
    yaw: input.yaw ?? null,
    pitch: input.pitch ?? null,
    meanLuma,
    n,
    noise: input.noise ?? null,
    mad: input.mad ?? null,
    rejects,
    totalSamples: input.totalSamples ?? n + rejects.total,
  };
}

/**
 * Port of build_profile from Python dms_face/calibration.py.
 * Returns a discriminated result: ok profile payload | failure with reason:
 * - 'too_dark': mean luma < 40
 * - 'no_face': no face detected / face not found
 * - 'head_turned': rejected primarily due to excessive head yaw/pitch
 * - 'too_few_samples': valid sample counts below minimum requirements
 * - 'eyes_not_shut': separation < 0.04 (open EAR and closed EAR too close together)
 */
export function buildProfile(
  openInput: PhaseInput,
  closedInput: PhaseInput,
  options?: BuildProfileOptions,
): BuildProfileResult {
  const minOpen = options?.minOpenSamples ?? MIN_OPEN_SAMPLES;
  const minClosed = options?.minClosedSamples ?? MIN_CLOSED_SAMPLES;
  const openResult = toPhaseResult(openInput, minOpen);
  const closedResult = toPhaseResult(closedInput, minClosed);

  // 1. Check lighting (too_dark)
  if (
    (openResult.meanLuma !== null && openResult.meanLuma < MIN_LUMA) ||
    (closedResult.meanLuma !== null && closedResult.meanLuma < MIN_LUMA)
  ) {
    return { ok: false, reason: 'too_dark' };
  }

  // 2. Check if EAR values are present
  if (
    openResult.ear === null ||
    closedResult.ear === null ||
    openResult.n === 0 ||
    closedResult.n === 0
  ) {
    const noFaceTotal = openResult.rejects.noFace + closedResult.rejects.noFace;
    const headTurnedTotal = openResult.rejects.headTurned + closedResult.rejects.headTurned;

    if (headTurnedTotal > noFaceTotal) {
      return { ok: false, reason: 'head_turned' };
    }
    if (noFaceTotal > 0 || openResult.ear === null || closedResult.ear === null) {
      return { ok: false, reason: 'no_face' };
    }
    return { ok: false, reason: 'too_few_samples' };
  }

  // 3. Check sample count minimums
  if (openResult.n < minOpen || closedResult.n < minClosed) {
    const noFaceTotal = openResult.rejects.noFace + closedResult.rejects.noFace;
    const headTurnedTotal = openResult.rejects.headTurned + closedResult.rejects.headTurned;

    if (headTurnedTotal > noFaceTotal && headTurnedTotal > 0) {
      return { ok: false, reason: 'head_turned' };
    }
    if (noFaceTotal > headTurnedTotal && noFaceTotal > 0) {
      return { ok: false, reason: 'no_face' };
    }
    return { ok: false, reason: 'too_few_samples' };
  }

  // 4. Check separation (eyes_not_shut)
  const earOpen = openResult.ear;
  const earClosed = closedResult.ear;
  const separation = earOpen - earClosed;
  const minSeparation = options?.minSeparation ?? MIN_SEPARATION;

  if (separation < minSeparation) {
    return { ok: false, reason: 'eyes_not_shut' };
  }

  // 5. Signal quality assessment
  const { quality, snr } = assessQuality(separation, openResult.noise);
  const payloadQuality: CalibrationQuality = quality === 'unknown' ? 'fair' : quality;

  const payload = toPhoneCalibrationPayload({
    earOpen,
    earClosed,
    snr: snr ?? 0,
    quality: payloadQuality,
    samplesOpen: openResult.n,
    samplesClosed: closedResult.n,
    created: options?.created,
  });

  return { ok: true, payload };
}
