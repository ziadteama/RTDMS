export type PhoneCalibrationValidationResult =
  | { ok: true }
  | { ok: false; error: string };

/**
 * Validates a phone_calibration payload according to contracts/pi-link CONTRACT.md
 * and contracts/pi-link/schemas/phone_calibration.schema.json.
 *
 * Rules:
 * - source must be 'phone'
 * - closed_ratio must be a number between 0.1 and 0.8
 * - ear_open must be a number between 0 (exclusive) and 1
 * - ear_closed must be a number between 0 and 1
 * - ear_open - ear_closed must be >= 0.04 (same gate as build_profile)
 * - snr must be a number >= 0
 * - quality must be 'good', 'fair', or 'poor'
 * - quality 'poor' is rejected by the Pi (HTTP 400)
 * - samples_open and samples_closed must be integers >= 1
 * - created must be a finite number
 */
export function validatePhoneCalibration(body: unknown): PhoneCalibrationValidationResult {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return { ok: false, error: 'body must be a JSON object' };
  }

  const b = body as Record<string, unknown>;

  if (b.source !== 'phone') {
    return { ok: false, error: "source must be 'phone'" };
  }

  if (typeof b.closed_ratio !== 'number' || Number.isNaN(b.closed_ratio)) {
    return { ok: false, error: 'closed_ratio must be a number' };
  }
  if (b.closed_ratio < 0.1 || b.closed_ratio > 0.8) {
    return { ok: false, error: 'closed_ratio out of range [0.1, 0.8]' };
  }

  if (typeof b.ear_open !== 'number' || Number.isNaN(b.ear_open) || b.ear_open <= 0 || b.ear_open > 1) {
    return { ok: false, error: 'ear_open must be between 0 (exclusive) and 1' };
  }

  if (typeof b.ear_closed !== 'number' || Number.isNaN(b.ear_closed) || b.ear_closed < 0 || b.ear_closed > 1) {
    return { ok: false, error: 'ear_closed must be between 0 and 1' };
  }

  if (b.ear_open - b.ear_closed < 0.04) {
    return { ok: false, error: 'separation too small: ear_open - ear_closed < 0.04' };
  }

  if (typeof b.snr !== 'number' || Number.isNaN(b.snr) || b.snr < 0) {
    return { ok: false, error: 'snr must be a non-negative number' };
  }

  if (b.quality !== 'good' && b.quality !== 'fair' && b.quality !== 'poor') {
    return { ok: false, error: "quality must be 'good', 'fair', or 'poor'" };
  }

  if (b.quality === 'poor') {
    return { ok: false, error: 'rejected: signal quality is poor' };
  }

  if (typeof b.samples_open !== 'number' || !Number.isInteger(b.samples_open) || b.samples_open < 1) {
    return { ok: false, error: 'samples_open must be an integer >= 1' };
  }

  if (typeof b.samples_closed !== 'number' || !Number.isInteger(b.samples_closed) || b.samples_closed < 1) {
    return { ok: false, error: 'samples_closed must be an integer >= 1' };
  }

  if (typeof b.created !== 'number' || !Number.isFinite(b.created)) {
    return { ok: false, error: 'created must be a finite timestamp' };
  }

  return { ok: true };
}
