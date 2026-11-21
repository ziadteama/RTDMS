import type { ReceiptStatus } from "../transport/WhatsAppTransport.ts";

export type SosStatus = "queued" | "sent" | "delivered" | "read" | "failed" | "opted_out";

export type OptInStatus = "pending" | "ok" | "opted_out" | "invalid" | "failed";

const SOS_STATUS_RANK: Record<"queued" | "sent" | "delivered" | "read", number> = {
  queued: 1,
  sent: 2,
  delivered: 3,
  read: 4,
};

export function nextSosStatus(current: SosStatus, receiptStatus: ReceiptStatus): SosStatus {
  if (current === "opted_out" || current === "failed") {
    return current;
  }

  if (receiptStatus === "failed") {
    return current === "queued" ? "failed" : current;
  }

  const currentRank = SOS_STATUS_RANK[current] ?? 0;
  const nextRank = SOS_STATUS_RANK[receiptStatus] ?? 0;

  return nextRank > currentRank ? receiptStatus : current;
}

export function nextOptInStatus(current: OptInStatus, receiptStatus: ReceiptStatus): OptInStatus {
  if (current === "opted_out" || current === "invalid") {
    return current;
  }

  if (receiptStatus === "failed") {
    return current === "pending" ? "failed" : current;
  }

  return "ok";
}
