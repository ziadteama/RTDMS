/**
 * Pure exponential backoff schedule calculator for connection retry.
 */

export const INITIAL_BACKOFF_MS = 1000;
export const MAX_BACKOFF_MS = 60000;

/**
 * Calculates next backoff delay in ms, doubling the current delay up to maxBackoffMs.
 */
export function computeNextBackoff(
  currentBackoffMs: number,
  maxBackoffMs: number = MAX_BACKOFF_MS,
): number {
  if (currentBackoffMs <= 0) {
    return INITIAL_BACKOFF_MS;
  }
  return Math.min(currentBackoffMs * 2, maxBackoffMs);
}
