/**
 * Pure functions for mapping Baileys receipt updates and extracting inbound text.
 */

import type { ReceiptStatus } from "./WhatsAppTransport.ts";

/**
 * Maps a Baileys message status (numeric or enum string) to a ReceiptStatus.
 * SERVER_ACK -> "sent"
 * DELIVERY_ACK -> "delivered"
 * READ / PLAYED -> "read"
 * ERROR -> "failed"
 */
export function mapBaileysStatusToReceiptStatus(
  status: number | string | null | undefined,
): ReceiptStatus | null {
  switch (status) {
    case 2:
    case "SERVER_ACK":
      return "sent";
    case 3:
    case "DELIVERY_ACK":
      return "delivered";
    case 4:
    case "READ":
    case 5:
    case "PLAYED":
      return "read";
    case 0:
    case "ERROR":
      return "failed";
    default:
      return null;
  }
}

/**
 * Maps a Baileys UserReceipt object to a ReceiptStatus.
 * readTimestamp or playedTimestamp -> "read"
 * receiptTimestamp -> "delivered"
 */
export function mapReceiptUpdateToStatus(receipt: {
  receiptTimestamp?: unknown;
  readTimestamp?: unknown;
  playedTimestamp?: unknown;
}): ReceiptStatus | null {
  if (receipt.playedTimestamp != null || receipt.readTimestamp != null) {
    return "read";
  }
  if (receipt.receiptTimestamp != null) {
    return "delivered";
  }
  return null;
}

/**
 * Extracts plain text from a Baileys inbound message content object.
 * Reads conversation or extendedTextMessage.text.
 * Returns null if no text message is found.
 */
export function extractInboundText(
  message:
    | {
        conversation?: string | null;
        extendedTextMessage?: { text?: string | null } | null;
      }
    | null
    | undefined,
): string | null {
  if (!message) {
    return null;
  }
  if (typeof message.conversation === "string" && message.conversation.length > 0) {
    return message.conversation;
  }
  if (
    typeof message.extendedTextMessage?.text === "string" &&
    message.extendedTextMessage.text.length > 0
  ) {
    return message.extendedTextMessage.text;
  }
  return null;
}
