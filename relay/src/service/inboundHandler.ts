import type { DatabaseSync } from "node:sqlite";
import type { WhatsAppTransport, InboundMessage, Receipt } from "../transport/WhatsAppTransport.ts";
import { type Logger, maskPhone } from "../log/Logger.ts";
import type { SosMemoryStore } from "../store/sosMemory.ts";
import { recordOptOut, updateContactStatusByOptInMessageId } from "../store/db.ts";

export interface SetupInboundParams {
  db: DatabaseSync;
  memoryStore: SosMemoryStore;
  transport: WhatsAppTransport;
  logger: Logger;
}

export function handleInboundMessage(
  msg: InboundMessage,
  db: DatabaseSync,
  logger: Logger,
): void {
  const trimmed = msg.text.trim().toLowerCase();
  if (trimmed !== "stop" && trimmed !== "stop.") {
    return;
  }

  recordOptOut(db, msg.from);
  logger.info("contact_opted_out", {
    phone: maskPhone(msg.from),
  });
}

export function handleReceipt(
  receipt: Receipt,
  db: DatabaseSync,
  memoryStore: SosMemoryStore,
): void {
  updateContactStatusByOptInMessageId(db, receipt.messageId, receipt.status);
  memoryStore.updateReceipt(receipt.messageId, receipt.status);
}

export function setupInboundAndReceipts(params: SetupInboundParams): void {
  const { db, memoryStore, transport, logger } = params;

  transport.onInbound((msg) => {
    handleInboundMessage(msg, db, logger);
  });

  transport.onReceipt((receipt) => {
    handleReceipt(receipt, db, memoryStore);
  });
}
