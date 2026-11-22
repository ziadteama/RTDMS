export type QualityRating = 'good' | 'fair' | 'poor' | 'unknown';

/**
 * Calculates the median of a list of numbers. Returns null if values is empty.
 * Matches Python's statistics.median.
 */
export function median(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[mid]!;
  }
  return (sorted[mid - 1]! + sorted[mid]!) / 2;
}

/**
 * Median absolute deviation -- a robust spread estimate.
 * Matches Python's CalibrationCollector._mad:
 * if len(values) < 5: return None
 * med = statistics.median(values)
 * return statistics.median([abs(v - med) for v in values])
 */
export function mad(values: readonly number[]): number | null {
  if (values.length < 5) return null;
  const med = median(values);
  if (med === null) return null;
  const deviations = values.map((v) => Math.abs(v - med));
  return median(deviations);
}

/**
 * Frame-to-frame jitter of the OPEN eye, with blinks excluded.
 * Matches Python's CalibrationCollector._open_state_noise:
 * Only samples at or above the median are used: below the median sits the
 * blink population, which is signal, not noise.
 */
export function openStateNoise(earValues: readonly number[]): number | null {
  if (earValues.length < 10) return null;
  const med = median(earValues);
  if (med === null) return null;
  const upper = earValues.filter((v) => v >= med);
  return mad(upper);
}

/**
 * Rate how usable this driver's eye signal is.
 * Matches Python's assess_quality:
 * SNR = separation / noise
 * good: SNR >= 4.0 / hysteresis_band (default 40 for band=0.10)
 * fair: SNR >= 2.0 / hysteresis_band (default 20 for band=0.10)
 * poor: anything less
 */
export function assessQuality(
  separation: number,
  noise: number | null,
  hysteresisBand = 0.10,
): { quality: QualityRating; snr: number | null } {
  if (noise === null || noise <= 1e-9) {
    return { quality: 'unknown', snr: null };
  }
  const snr = separation / noise;
  if (snr >= 4.0 / hysteresisBand) {
    return { quality: 'good', snr };
  }
  if (snr >= 2.0 / hysteresisBand) {
    return { quality: 'fair', snr };
  }
  return { quality: 'poor', snr };
}
