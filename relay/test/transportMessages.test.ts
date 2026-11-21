import { describe, expect, it } from "vitest";
import {
  mapBaileysStatusToReceiptStatus,
  mapReceiptUpdateToStatus,
  extractInboundText,
} from "../src/transport/baileysMessages.ts";

describe("baileysMessages pure functions", () => {
  describe("mapBaileysStatusToReceiptStatus", () => {
    it("maps SERVER_ACK (2) to sent", () => {
      expect(mapBaileysStatusToReceiptStatus(2)).toBe("sent");
      expect(mapBaileysStatusToReceiptStatus("SERVER_ACK")).toBe("sent");
    });

    it("maps DELIVERY_ACK (3) to delivered", () => {
      expect(mapBaileysStatusToReceiptStatus(3)).toBe("delivered");
      expect(mapBaileysStatusToReceiptStatus("DELIVERY_ACK")).toBe("delivered");
    });

    it("maps READ (4) and PLAYED (5) to read", () => {
      expect(mapBaileysStatusToReceiptStatus(4)).toBe("read");
      expect(mapBaileysStatusToReceiptStatus("READ")).toBe("read");
      expect(mapBaileysStatusToReceiptStatus(5)).toBe("read");
      expect(mapBaileysStatusToReceiptStatus("PLAYED")).toBe("read");
    });

    it("maps ERROR (0) to failed", () => {
      expect(mapBaileysStatusToReceiptStatus(0)).toBe("failed");
      expect(mapBaileysStatusToReceiptStatus("ERROR")).toBe("failed");
    });

    it("returns null for PENDING (1) or unmapped statuses", () => {
      expect(mapBaileysStatusToReceiptStatus(1)).toBeNull();
      expect(mapBaileysStatusToReceiptStatus("PENDING")).toBeNull();
      expect(mapBaileysStatusToReceiptStatus(999)).toBeNull();
      expect(mapBaileysStatusToReceiptStatus(null)).toBeNull();
      expect(mapBaileysStatusToReceiptStatus(undefined)).toBeNull();
    });
  });

  describe("mapReceiptUpdateToStatus", () => {
    it("maps playedTimestamp to read", () => {
      expect(mapReceiptUpdateToStatus({ playedTimestamp: 1795189200 })).toBe("read");
    });

    it("maps readTimestamp to read", () => {
      expect(mapReceiptUpdateToStatus({ readTimestamp: 1795189200 })).toBe("read");
    });

    it("maps receiptTimestamp to delivered", () => {
      expect(mapReceiptUpdateToStatus({ receiptTimestamp: 1795189200 })).toBe("delivered");
    });

    it("prioritizes read over receipt timestamp when both present", () => {
      expect(
        mapReceiptUpdateToStatus({
          receiptTimestamp: 1795189100,
          readTimestamp: 1795189200,
        }),
      ).toBe("read");
    });

    it("returns null when no timestamps present", () => {
      expect(mapReceiptUpdateToStatus({})).toBeNull();
      expect(
        mapReceiptUpdateToStatus({
          receiptTimestamp: null,
          readTimestamp: undefined,
        }),
      ).toBeNull();
    });
  });

  describe("extractInboundText", () => {
    it("extracts text from conversation string", () => {
      const msg = { conversation: "STOP" };
      expect(extractInboundText(msg)).toBe("STOP");
    });

    it("extracts text from extendedTextMessage", () => {
      const msg = {
        extendedTextMessage: {
          text: "stop please",
        },
      };
      expect(extractInboundText(msg)).toBe("stop please");
    });

    it("prefers non-empty conversation text if available", () => {
      const msg = {
        conversation: "YES",
        extendedTextMessage: { text: "NO" },
      };
      expect(extractInboundText(msg)).toBe("YES");
    });

    it("returns null for messages without text content", () => {
      expect(extractInboundText(null)).toBeNull();
      expect(extractInboundText(undefined)).toBeNull();
      expect(extractInboundText({})).toBeNull();
      expect(extractInboundText({ conversation: "" })).toBeNull();
      expect(extractInboundText({ extendedTextMessage: { text: "" } })).toBeNull();
      expect(extractInboundText({ extendedTextMessage: null })).toBeNull();
    });
  });
});
