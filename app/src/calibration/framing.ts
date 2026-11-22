import { MIN_LUMA } from './build-profile';
import type { EarSample, FramingStatus } from './types';

/**
 * Pure helper for the calibration framing step.
 * Checks:
 * - faceInOval: face present and faceBoxFraction between 0.25 and 0.8
 * - lightOk: luma >= 40
 * - headStraight: |yaw| <= 15 && |pitch| <= 15
 */
export function framingStatus(
  sample: Pick<EarSample, 'faceFound' | 'faceBoxFraction' | 'luma' | 'yaw' | 'pitch'>,
): FramingStatus {
  const faceInOval =
    sample.faceFound &&
    sample.faceBoxFraction >= 0.25 &&
    sample.faceBoxFraction <= 0.8;
  const lightOk = sample.luma >= MIN_LUMA;
  const headStraight =
    sample.yaw !== null &&
    sample.pitch !== null &&
    Math.abs(sample.yaw) <= 15 &&
    Math.abs(sample.pitch) <= 15;

  return { faceInOval, lightOk, headStraight };
}
