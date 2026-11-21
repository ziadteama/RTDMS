import { describe, expect, it } from "vitest";
import {
  computeNextBackoff,
  INITIAL_BACKOFF_MS,
  MAX_BACKOFF_MS,
} from "../src/transport/baileysBackoff.ts";

describe("baileysBackoff pure functions", () => {
  it("initial backoff is 1000ms", () => {
    expect(INITIAL_BACKOFF_MS).toBe(1000);
  });

  it("max backoff is 60000ms", () => {
    expect(MAX_BACKOFF_MS).toBe(60000);
  });

  it("doubles backoff through the exponential schedule", () => {
    expect(computeNextBackoff(1000)).toBe(2000);
    expect(computeNextBackoff(2000)).toBe(4000);
    expect(computeNextBackoff(4000)).toBe(8000);
    expect(computeNextBackoff(8000)).toBe(16000);
    expect(computeNextBackoff(16000)).toBe(32000);
  });

  it("caps backoff at 60000ms (60s)", () => {
    expect(computeNextBackoff(32000)).toBe(60000);
    expect(computeNextBackoff(60000)).toBe(60000);
    expect(computeNextBackoff(100000)).toBe(60000);
  });

  it("supports custom max backoff parameter", () => {
    expect(computeNextBackoff(1000, 1500)).toBe(1500);
    expect(computeNextBackoff(5000, 8000)).toBe(8000);
  });

  it("returns initial backoff if input is zero or negative", () => {
    expect(computeNextBackoff(0)).toBe(INITIAL_BACKOFF_MS);
    expect(computeNextBackoff(-500)).toBe(INITIAL_BACKOFF_MS);
  });
});
