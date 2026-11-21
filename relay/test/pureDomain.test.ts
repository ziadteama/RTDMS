import { describe, it, expect } from "vitest";
import { buildOptInMessage, buildSosMessage, formatCrashTime } from "../src/domain/messages.ts";
import { SlidingWindowLimiter } from "../src/domain/limiter.ts";
import { nextSosStatus, nextOptInStatus } from "../src/domain/statusRank.ts";
import {
  isValidPhone,
  isValidUuid,
  validateCoordinates,
  validateRegisterPayload,
  validateSosPayload,
} from "../src/domain/validate.ts";

describe("messages domain", () => {
  it("builds opt-in message with driver name", () => {
    const msg = buildOptInMessage("  Ziad  ");
    expect(msg).toBe(
      "Ziad added you as an emergency contact in Sahi. You will get a message if their car's crash alert fires. Reply STOP to opt out.",
    );
  });

  it("formats crash time in specified timezone (Africa/Cairo default)", () => {
    // 1795189200000 is 2026-11-21 17:40:00 UTC (19:40 in Cairo UTC+2)
    const formatted = formatCrashTime(1795189200000, "Africa/Cairo");
    expect(formatted).toMatch(/\d{1,2}:\d{2}\s+(AM|PM)/);
  });

  it("builds crash alert message with 5 decimal coordinates and Google Maps link", () => {
    const text = buildSosMessage({
      kind: "crash",
      driverName: "Ziad",
      tCrash: 1795189200000,
      lat: 30.0444,
      lon: 31.2357,
      tz: "Africa/Cairo",
    });
    expect(text).toContain("SAHI crash alert");
    expect(text).toContain("Ziad may need help");
    expect(text).toContain("Location: 30.04440,31.23570 https://maps.google.com/?q=30.04440,31.23570");
  });

  it("builds crash alert message with Location unknown when lat/lon are null", () => {
    const text = buildSosMessage({
      kind: "crash",
      driverName: "Ziad",
      tCrash: 1795189200000,
      lat: null,
      lon: null,
      tz: "Africa/Cairo",
    });
    expect(text).toContain("SAHI crash alert");
    expect(text).toContain("Ziad may need help. Location unknown");
  });

  it("builds manual alert message without the word crash", () => {
    const text = buildSosMessage({
      kind: "manual",
      driverName: "Ziad",
      tCrash: 1795189200000,
      lat: 30.0444,
      lon: 31.2357,
      tz: "Africa/Cairo",
    });
    expect(text).toContain("SAHI alert");
    expect(text).not.toContain("crash");
    expect(text).toContain("Ziad needs help");
    expect(text).toContain("Location: 30.04440,31.23570 https://maps.google.com/?q=30.04440,31.23570");
  });
});

describe("limiter domain", () => {
  it("enforces sliding window limits and calculates retryAfterSec", () => {
    let now = 10000;
    const limiter = new SlidingWindowLimiter(() => now);

    for (let i = 0; i < 3; i++) {
      const res = limiter.check("test-key", 3, 1000);
      expect(res.allowed).toBe(true);
    }

    const blocked = limiter.check("test-key", 3, 1000);
    expect(blocked.allowed).toBe(false);
    expect(blocked.retryAfterSec).toBe(1);

    now += 1001;
    const unblocked = limiter.check("test-key", 3, 1000);
    expect(unblocked.allowed).toBe(true);
  });
});

describe("statusRank domain", () => {
  it("receipts only move forward and failed only transitions from queued", () => {
    expect(nextSosStatus("queued", "sent")).toBe("sent");
    expect(nextSosStatus("sent", "delivered")).toBe("delivered");
    expect(nextSosStatus("delivered", "read")).toBe("read");

    // never backwards
    expect(nextSosStatus("read", "delivered")).toBe("read");
    expect(nextSosStatus("read", "sent")).toBe("read");
    expect(nextSosStatus("delivered", "sent")).toBe("delivered");

    // failed only from queued
    expect(nextSosStatus("queued", "failed")).toBe("failed");
    expect(nextSosStatus("sent", "failed")).toBe("sent");
    expect(nextSosStatus("delivered", "failed")).toBe("delivered");
    expect(nextSosStatus("read", "failed")).toBe("read");

    // opted_out terminal
    expect(nextSosStatus("opted_out", "read")).toBe("opted_out");
  });

  it("opt-in status transitions to ok or failed", () => {
    expect(nextOptInStatus("pending", "sent")).toBe("ok");
    expect(nextOptInStatus("pending", "delivered")).toBe("ok");
    expect(nextOptInStatus("pending", "read")).toBe("ok");
    expect(nextOptInStatus("pending", "failed")).toBe("failed");
    expect(nextOptInStatus("opted_out", "delivered")).toBe("opted_out");
    expect(nextOptInStatus("invalid", "delivered")).toBe("invalid");
  });
});

describe("validate domain", () => {
  it("validates E.164 phone numbers", () => {
    expect(isValidPhone("+201000000001")).toBe(true);
    expect(isValidPhone("+12025550143")).toBe(true);
    expect(isValidPhone("01000000001")).toBe(false);
    expect(isValidPhone("+0123456789")).toBe(false);
    expect(isValidPhone("invalid")).toBe(false);
  });

  it("validates UUIDs", () => {
    expect(isValidUuid("c7bf3b61-e2c6-4d08-82a5-968ac9bfca50")).toBe(true);
    expect(isValidUuid("not-a-uuid")).toBe(false);
  });

  it("validates coordinates", () => {
    expect(validateCoordinates(null, null)).toEqual({ lat: null, lon: null });
    expect(validateCoordinates(30.0444, 31.2357)).toEqual({ lat: 30.0444, lon: 31.2357 });
    expect(validateCoordinates(null, 31.2357)).toBeNull();
    expect(validateCoordinates(30.0444, null)).toBeNull();
    expect(validateCoordinates(95, 31.2357)).toBeNull();
    expect(validateCoordinates(30.0444, 200)).toBeNull();
  });

  it("collapses duplicates in register payload and rejects > 5 contacts", () => {
    const payloadWithDups = {
      driver_name: "Ziad",
      contacts: [
        { name: "Mum", phone: "+201000000001" },
        { name: "Mother", phone: "+201000000001" },
        { name: "Dad", phone: "+201000000002" },
      ],
    };
    const res = validateRegisterPayload(payloadWithDups);
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.data.contacts.length).toBe(2);
      expect(res.data.contacts[0]?.name).toBe("Mum");
    }

    const payloadTooMany = {
      driver_name: "Ziad",
      contacts: [
        { name: "C1", phone: "+201000000001" },
        { name: "C2", phone: "+201000000002" },
        { name: "C3", phone: "+201000000003" },
        { name: "C4", phone: "+201000000004" },
        { name: "C5", phone: "+201000000005" },
        { name: "C6", phone: "+201000000006" },
      ],
    };
    expect(validateRegisterPayload(payloadTooMany)).toEqual({
      ok: false,
      error: "too_many_contacts",
    });
  });

  it("validates SOS payload", () => {
    const validSos = {
      client_id: "c7bf3b61-e2c6-4d08-82a5-968ac9bfca50",
      kind: "crash",
      t_crash: 1795189200000,
      lat: 30.0444,
      lon: 31.2357,
    };
    expect(validateSosPayload(validSos).ok).toBe(true);

    const invalidKind = { ...validSos, kind: "unknown" };
    expect(validateSosPayload(invalidKind)).toEqual({ ok: false, error: "invalid_kind" });
  });
});
