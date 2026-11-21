/**
 * Dry-run WhatsApp transport for safe local testing and development.
 * Never connects to WhatsApp or sends real network traffic.
 */

import { randomUUID } from "node:crypto";
import type {
  WhatsAppTransport,
  TransportStatus,
  Receipt,
  InboundMessage,
} from "./WhatsAppTransport.ts";
import type { Logger } from "../log/Logger.ts";
import { maskPhone } from "../log/Logger.ts";

export function createDryRunTransport(log: Logger): WhatsAppTransport {
  let receiptListener: ((receipt: Receipt) => void) | null = null;
  let inboundListener: ((message: InboundMessage) => void) | null = null;

  return {
    async send(text: string, to: string): Promise<string> {
      const messageId = `dry_${randomUUID()}`;
      log.info("dry_run_send", {
        to: maskPhone(to),
        length: text.length,
      });

      const sentTimer = setTimeout(() => {
        receiptListener?.({ messageId, status: "sent" });
        const delivTimer = setTimeout(() => {
          receiptListener?.({ messageId, status: "delivered" });
        }, 50);
        delivTimer.unref();
      }, 50);
      sentTimer.unref();

      return messageId;
    },

    onReceipt(listener: (receipt: Receipt) => void): void {
      receiptListener = listener;
    },

    onInbound(listener: (message: InboundMessage) => void): void {
      inboundListener = listener;
      void inboundListener;
    },

    status(): TransportStatus {
      return "connected";
    },
  };
}
