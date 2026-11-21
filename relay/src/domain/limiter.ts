export type Clock = () => number;

export interface LimiterCheckResult {
  allowed: boolean;
  retryAfterSec?: number;
}

export interface RateLimiter {
  check(key: string, limit: number, windowMs: number): LimiterCheckResult;
}

export class SlidingWindowLimiter implements RateLimiter {
  private readonly records = new Map<string, number[]>();
  private readonly clock: Clock;

  constructor(clock: Clock = Date.now) {
    this.clock = clock;
  }

  check(key: string, limit: number, windowMs: number): LimiterCheckResult {
    const now = this.clock();
    const threshold = now - windowMs;

    const existing = this.records.get(key) ?? [];
    const valid = existing.filter((ts) => ts > threshold);

    if (valid.length >= limit) {
      const oldest = valid[0] ?? now;
      const retryAfterMs = oldest + windowMs - now;
      const retryAfterSec = Math.max(1, Math.ceil(retryAfterMs / 1000));
      this.records.set(key, valid);
      return { allowed: false, retryAfterSec };
    }

    valid.push(now);
    this.records.set(key, valid);
    return { allowed: true };
  }
}
