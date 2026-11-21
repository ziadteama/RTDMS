/**
 * Baileys WhatsApp transport implementation.
 * Wraps @whiskeysockets/baileys 6.7.24 to provide WhatsApp connectivity.
 */

import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  type ConnectionState,
  type WASocket,
  type WAMessageUpdate,
  type MessageUserReceiptUpdate,
  type WAMessage,
} from "@whiskeysockets/baileys";
import { pino } from "pino";
import type {
  WhatsAppTransport,
  TransportStatus,
  Receipt,
  InboundMessage,
} from "./WhatsAppTransport.ts";
import type { Logger } from "../log/Logger.ts";
import { maskPhone } from "../log/Logger.ts";
import { e164ToJid, jidToE164, isLidJid, isUserJid } from "./baileysPhone.ts";
import {
  mapBaileysStatusToReceiptStatus,
  mapReceiptUpdateToStatus,
  extractInboundText,
} from "./baileysMessages.ts";
import {
  computeNextBackoff,
  INITIAL_BACKOFF_MS,
  MAX_BACKOFF_MS,
} from "./baileysBackoff.ts";

function printPairingInstructions(qr: string): void {
  console.log("\n" + "=".repeat(64));
  console.log("WHATSAPP PAIRING QR CODE:");
  console.log(qr);
  console.log("Scan via WhatsApp on phone: Settings > Linked Devices > Link a Device.");
  console.log('To render as terminal QR: qrencode -t ANSIUTF8 "' + qr + '"');
  console.log("=".repeat(64) + "\n");
}

function isLoggedOutReason(lastDisconnect: unknown): boolean {
  const err = (lastDisconnect as { error?: unknown })?.error;
  const statusCode =
    (err as { output?: { statusCode?: number }; statusCode?: number })?.output?.statusCode ??
    (err as { statusCode?: number })?.statusCode;
  return statusCode === DisconnectReason.loggedOut;
}

class BaileysTransportImpl implements WhatsAppTransport {
  private sock: WASocket | null = null;
  private currentStatus: TransportStatus = "disconnected";
  private backoffMs = INITIAL_BACKOFF_MS;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private isLoggedOut = false;
  private receiptListener: ((receipt: Receipt) => void) | null = null;
  private inboundListener: ((message: InboundMessage) => void) | null = null;

  constructor(private readonly opts: { authDir: string; log: Logger }) {
    void this.connect();
  }

  private scheduleReconnect(): void {
    if (this.isLoggedOut) {
      return;
    }
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    const delay = this.backoffMs;
    this.backoffMs = computeNextBackoff(this.backoffMs, MAX_BACKOFF_MS);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      void this.connect();
    }, delay);
    this.reconnectTimer.unref();
  }

  private handleMessagesUpdate(updates: WAMessageUpdate[]): void {
    for (const item of updates) {
      if (!item.key?.fromMe || !item.key.id) {
        continue;
      }
      const status = mapBaileysStatusToReceiptStatus(item.update?.status);
      if (status && this.receiptListener) {
        this.receiptListener({ messageId: item.key.id, status });
      }
    }
  }

  private handleReceiptUpdate(receipts: MessageUserReceiptUpdate[]): void {
    for (const item of receipts) {
      if (!item.key?.fromMe || !item.key.id) {
        continue;
      }
      const status = mapReceiptUpdateToStatus(item.receipt);
      if (status && this.receiptListener) {
        this.receiptListener({ messageId: item.key.id, status });
      }
    }
  }

  private handleMessagesUpsert(upsert: { messages: WAMessage[]; type: string }): void {
    if (upsert.type !== "notify") {
      return;
    }
    for (const msg of upsert.messages) {
      if (msg.key?.fromMe) {
        continue;
      }
      const jid = msg.key?.remoteJid;
      if (!jid) {
        continue;
      }
      if (isLidJid(jid)) {
        this.opts.log.info("baileys_inbound_lid_skipped", { jid: maskPhone(jid) });
        continue;
      }
      if (!isUserJid(jid)) {
        continue;
      }
      const from = jidToE164(jid);
      const text = extractInboundText(msg.message);
      if (from && text && this.inboundListener) {
        this.inboundListener({ from, text });
      }
    }
  }

  private handleConnectionUpdate(update: Partial<ConnectionState>): void {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      this.currentStatus = "pairing";
      printPairingInstructions(qr);
      this.opts.log.info("whatsapp_qr_emitted");
    }
    if (connection === "open") {
      this.currentStatus = "connected";
      this.backoffMs = INITIAL_BACKOFF_MS;
      this.opts.log.info("whatsapp_connected");
    } else if (connection === "close") {
      this.currentStatus = "disconnected";
      if (isLoggedOutReason(lastDisconnect)) {
        this.isLoggedOut = true;
        this.opts.log.error("whatsapp_logged_out", {
          reason: "Session logged out from WhatsApp. Delete auth dir and re-pair.",
        });
        return;
      }
      this.opts.log.warn("whatsapp_disconnected", { retryInMs: this.backoffMs });
      this.scheduleReconnect();
    }
  }

  private async connect(): Promise<void> {
    if (this.isLoggedOut) {
      return;
    }
    try {
      const { state, saveCreds } = await useMultiFileAuthState(this.opts.authDir);
      this.sock = makeWASocket({
        auth: state,
        logger: pino({ level: "silent" }),
        printQRInTerminal: false,
      });

      this.sock.ev.on("creds.update", saveCreds);
      this.sock.ev.on("connection.update", (u) => this.handleConnectionUpdate(u));
      this.sock.ev.on("messages.update", (u) => this.handleMessagesUpdate(u));
      this.sock.ev.on("message-receipt.update", (r) => this.handleReceiptUpdate(r));
      this.sock.ev.on("messages.upsert", (m) => this.handleMessagesUpsert(m));
    } catch (err) {
      this.opts.log.error("whatsapp_init_error", {
        reason: err instanceof Error ? err.message : String(err),
      });
      this.scheduleReconnect();
    }
  }

  async send(text: string, to: string): Promise<string> {
    if (this.currentStatus !== "connected" || !this.sock) {
      throw new Error("not_connected");
    }
    const jid = e164ToJid(to);
    if (!jid) {
      throw new Error("not_on_whatsapp");
    }
    const check = await this.sock.onWhatsApp(jid);
    const exists = check && check.length > 0 && Boolean(check[0]?.exists);
    if (!exists) {
      throw new Error("not_on_whatsapp");
    }
    const sent = await this.sock.sendMessage(jid, { text });
    const messageId = sent?.key?.id;
    if (!messageId) {
      throw new Error("send_failed");
    }
    return messageId;
  }

  onReceipt(listener: (receipt: Receipt) => void): void {
    this.receiptListener = listener;
  }

  onInbound(listener: (message: InboundMessage) => void): void {
    this.inboundListener = listener;
  }

  status(): TransportStatus {
    return this.currentStatus;
  }
}

export function createBaileysTransport(opts: {
  authDir: string;
  log: Logger;
}): WhatsAppTransport {
  return new BaileysTransportImpl(opts);
}
