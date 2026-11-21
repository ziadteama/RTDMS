import type { ReceiptStatus } from "../transport/WhatsAppTransport.ts";
import { type SosStatus, nextSosStatus } from "../domain/statusRank.ts";

export interface SosContactResult {
  phone: string;
  phone_last4: string;
  messageId?: string;
  status: SosStatus;
}

export interface SosRecord {
  clientId: string;
  installId: string;
  createdAt: number;
  results: SosContactResult[];
}

export interface SosMemoryOptions {
  clock?: () => number;
  ttlMs?: number;
  cleanupIntervalMs?: number;
}

const DEFAULT_TTL_MS = 24 * 60 * 60 * 1000;
const DEFAULT_INTERVAL_MS = 60 * 1000;

export class SosMemoryStore {
  private readonly records = new Map<string, SosRecord>();
  private readonly messageIndex = new Map<string, { clientId: string; phone: string }>();
  private readonly clock: () => number;
  private readonly ttlMs: number;
  private readonly intervalId: NodeJS.Timeout;

  constructor(opts: SosMemoryOptions = {}) {
    this.clock = opts.clock ?? Date.now;
    this.ttlMs = opts.ttlMs ?? DEFAULT_TTL_MS;
    const intervalMs = opts.cleanupIntervalMs ?? DEFAULT_INTERVAL_MS;

    this.intervalId = setInterval(() => {
      this.pruneExpired();
    }, intervalMs);
    this.intervalId.unref();
  }

  save(record: SosRecord): void {
    this.records.set(record.clientId, record);
    for (const r of record.results) {
      if (r.messageId) {
        this.messageIndex.set(r.messageId, { clientId: record.clientId, phone: r.phone });
      }
    }
  }

  get(clientId: string): SosRecord | null {
    const record = this.records.get(clientId);
    if (!record) return null;
    if (this.clock() - record.createdAt > this.ttlMs) {
      this.deleteRecord(clientId);
      return null;
    }
    return record;
  }

  getByInstallAndClient(installId: string, clientId: string): SosRecord | null {
    const record = this.get(clientId);
    if (!record || record.installId !== installId) {
      return null;
    }
    return record;
  }

  updateMessageId(clientId: string, phone: string, messageId: string): void {
    const record = this.records.get(clientId);
    if (!record) return;
    const contact = record.results.find((c) => c.phone === phone);
    if (contact) {
      contact.messageId = messageId;
      this.messageIndex.set(messageId, { clientId, phone });
    }
  }

  updateContactStatus(clientId: string, phone: string, status: SosStatus): void {
    const record = this.records.get(clientId);
    if (!record) return;
    const contact = record.results.find((c) => c.phone === phone);
    if (contact) {
      contact.status = status;
    }
  }

  updateReceipt(messageId: string, receiptStatus: ReceiptStatus): boolean {
    const mapping = this.messageIndex.get(messageId);
    if (!mapping) return false;
    const record = this.get(mapping.clientId);
    if (!record) return false;
    const contact = record.results.find((c) => c.phone === mapping.phone);
    if (!contact) return false;
    contact.status = nextSosStatus(contact.status, receiptStatus);
    return true;
  }

  deleteByInstall(installId: string): void {
    for (const [clientId, record] of this.records.entries()) {
      if (record.installId === installId) {
        this.deleteRecord(clientId);
      }
    }
  }

  pruneExpired(): void {
    const now = this.clock();
    for (const [clientId, record] of this.records.entries()) {
      if (now - record.createdAt > this.ttlMs) {
        this.deleteRecord(clientId);
      }
    }
  }

  close(): void {
    clearInterval(this.intervalId);
  }

  private deleteRecord(clientId: string): void {
    const record = this.records.get(clientId);
    if (record) {
      for (const res of record.results) {
        if (res.messageId) {
          this.messageIndex.delete(res.messageId);
        }
      }
      this.records.delete(clientId);
    }
  }
}
