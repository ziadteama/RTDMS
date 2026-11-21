/** The only thing the business logic knows about WhatsApp. Implementations: Baileys, Fake, DryRun. */

export type TransportStatus = "connected" | "disconnected" | "pairing";

export type ReceiptStatus = "sent" | "delivered" | "read" | "failed";

export interface Receipt {
  /** Opaque id returned by send(). */
  messageId: string;
  status: ReceiptStatus;
}

export interface InboundMessage {
  /** E.164 sender, e.g. +201000000001. */
  from: string;
  text: string;
}

export interface WhatsAppTransport {
  /** Sends a text message. Resolves with an opaque message id; rejects on failure. */
  send(text: string, to: string): Promise<string>;
  /** Registers the (single) receipt listener. */
  onReceipt(listener: (receipt: Receipt) => void): void;
  /** Registers the (single) inbound-message listener. */
  onInbound(listener: (message: InboundMessage) => void): void;
  status(): TransportStatus;
}
