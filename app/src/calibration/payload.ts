import type { CalibrationQuality, PhoneCalibrationPayload } from './types';

export type CreatePayloadParams = {
  earOpen: number;
  earClosed: number;
  snr: number;
  quality: CalibrationQuality;
  samplesOpen: number;
  samplesClosed: number;
  created?: number;
};

/**
 * Maps raw calibration values to the phone_calibration contract payload.
 * closed_ratio is clipped to schema range [0.1, 0.8].
 */
export function toPhoneCalibrationPayload(params: CreatePayloadParams): PhoneCalibrationPayload {
  const rawRatio = params.earOpen > 0 ? params.earClosed / params.earOpen : 0.1;
  const closedRatio = Number(Math.max(0.1, Math.min(0.8, rawRatio)).toFixed(4));
  return {
    source: 'phone',
    closed_ratio: closedRatio,
    ear_open: Number(params.earOpen.toFixed(4)),
    ear_closed: Number(params.earClosed.toFixed(4)),
    snr: Number(Math.max(0, params.snr).toFixed(1)),
    quality: params.quality,
    samples_open: params.samplesOpen,
    samples_closed: params.samplesClosed,
    created: params.created ?? Date.now(),
  };
}
