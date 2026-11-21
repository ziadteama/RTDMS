import { describe, expect, it } from "vitest";
import {
  e164ToJid,
  jidToE164,
  isLidJid,
  isUserJid,
} from "../src/transport/baileysPhone.ts";

describe("baileysPhone pure functions", () => {
  describe("e164ToJid", () => {
    it("converts a valid Egyptian E.164 number to a WhatsApp JID", () => {
      expect(e164ToJid("+201000000001")).toBe("201000000001@s.whatsapp.net");
      expect(e164ToJid("+201000000099")).toBe("201000000099@s.whatsapp.net");
    });

    it("converts other international E.164 numbers", () => {
      expect(e164ToJid("+12025550143")).toBe("12025550143@s.whatsapp.net");
      expect(e164ToJid("+447700900077")).toBe("447700900077@s.whatsapp.net");
    });

    it("returns null for numbers without a leading plus", () => {
      expect(e164ToJid("201000000001")).toBeNull();
    });

    it("returns null for non-numeric characters", () => {
      expect(e164ToJid("+20100abc0001")).toBeNull();
      expect(e164ToJid("+20 100 000 0001")).toBeNull();
      expect(e164ToJid("+20-100-000-0001")).toBeNull();
    });

    it("returns null for numbers that are too short or too long", () => {
      expect(e164ToJid("+12345")).toBeNull();
      expect(e164ToJid("+12345678901234567890")).toBeNull();
    });

    it("returns null for empty strings", () => {
      expect(e164ToJid("")).toBeNull();
    });
  });

  describe("jidToE164", () => {
    it("converts standard 1:1 user JID to E.164", () => {
      expect(jidToE164("201000000001@s.whatsapp.net")).toBe("+201000000001");
    });

    it("converts user JID with device index to E.164", () => {
      expect(jidToE164("201000000001:2@s.whatsapp.net")).toBe("+201000000001");
      expect(jidToE164("12025550143:0@s.whatsapp.net")).toBe("+12025550143");
    });

    it("returns null for group JIDs", () => {
      expect(jidToE164("123456789-987654@g.us")).toBeNull();
    });

    it("returns null for broadcast JIDs", () => {
      expect(jidToE164("status@broadcast")).toBeNull();
    });

    it("returns null for LID JIDs", () => {
      expect(jidToE164("1234567890@lid")).toBeNull();
    });

    it("returns null for invalid or non-numeric user parts", () => {
      expect(jidToE164("invalid@s.whatsapp.net")).toBeNull();
      expect(jidToE164("123@s.whatsapp.net")).toBeNull();
      expect(jidToE164("")).toBeNull();
    });
  });

  describe("isLidJid", () => {
    it("returns true for LID JIDs", () => {
      expect(isLidJid("1234567890@lid")).toBe(true);
    });

    it("returns false for regular user and group JIDs", () => {
      expect(isLidJid("201000000001@s.whatsapp.net")).toBe(false);
      expect(isLidJid("123456789@g.us")).toBe(false);
    });
  });

  describe("isUserJid", () => {
    it("returns true for user JIDs", () => {
      expect(isUserJid("201000000001@s.whatsapp.net")).toBe(true);
      expect(isUserJid("201000000001:1@s.whatsapp.net")).toBe(true);
    });

    it("returns false for non-user JIDs", () => {
      expect(isUserJid("123456789@g.us")).toBe(false);
      expect(isUserJid("status@broadcast")).toBe(false);
      expect(isUserJid("1234567890@lid")).toBe(false);
    });
  });
});
