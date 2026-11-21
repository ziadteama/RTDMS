import type {
  InboundMessage,
  Receipt,
  ReceiptStatus,
  TransportStatus,
  WhatsAppTransport,
} from "./WhatsAppTransport.ts";

export interface SentMessage {
  to: string;
  text: string;
  messageId: string;
}

export class FakeTransport implements WhatsAppTransport {
  public sent: SentMessage[] = [];
  private currentStatus: TransportStatus = "connected";
  private receiptListener: ((receipt: Receipt) => void) | null = null;
  private inboundListener: ((message: InboundMessage) => void) | null = null;
  private nextSendError: Error | null = null;
  private notOnWhatsAppNumbers = new Set<string>();
  private messageCounter = 0;

  status(): TransportStatus {
    return this.currentStatus;
  }

  setStatus(status: TransportStatus): void {
    this.currentStatus = status;
  }

  failNextSend(err?: Error): void {
    this.nextSendError = err ?? new Error("fake send failure");
  }

  markNotOnWhatsApp(phone: string): void {
    this.notOnWhatsAppNumbers.add(phone.trim());
  }

  emitReceipt(messageId: string, status: ReceiptStatus): void {
    if (this.receiptListener) {
      this.receiptListener({ messageId, status });
    }
  }

  emitInbound(from: string, text: string): void {
    if (this.inboundListener) {
      this.inboundListener({ from, text });
    }
  }

  onReceipt(listener: (receipt: Receipt) => void): void {
    this.receiptListener = listener;
  }

  onInbound(listener: (message: InboundMessage) => void): void {
    this.inboundListener = listener;
  }

  async send(text: string, to: string): Promise<string> {
    if (this.nextSendError) {
      const err = this.nextSendError;
      this.nextSendError = null;
      throw err;
    }

    if (this.notOnWhatsAppNumbers.has(to.trim())) {
      throw new Error("recipient is not_on_whatsapp");
    }

    this.messageCounter += 1;
    const messageId = `fake-msg-${this.messageCounter}`;
    this.sent.push({ to, text, messageId });
    return messageId;
  }
}
