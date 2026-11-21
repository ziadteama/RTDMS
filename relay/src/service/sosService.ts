import type { DatabaseSync } from "node:sqlite";
import type { WhatsAppTransport } from "../transport/WhatsAppTransport.ts";
import type { Logger } from "../log/Logger.ts";
import type { RateLimiter } from "../domain/limiter.ts";
import type { SosContactResult, SosMemoryStore } from "../store/sosMemory.ts";
import type { SosStatus } from "../domain/statusRank.ts";
import { getInstall, getContacts, isOptedOut } from "../store/db.ts";
import { buildSosMessage } from "../domain/messages.ts";

export interface SosServiceParams {
  installId: string;
  clientId: string;
  kind: "crash" | "manual";
  tCrash: number;
  lat: number | null;
  lon: number | null;
  db: DatabaseSync;
  memoryStore: SosMemoryStore;
  transport: WhatsAppTransport;
  limiter: RateLimiter;
  logger: Logger;
  now: number;
  tz?: string;
}

export type SosServiceResult =
  | {
      ok: true;
      clientId: string;
      results: Array<{ phone_last4: string; status: SosStatus }>;
    }
  | {
      ok: false;
      status: number;
      error: string;
      retryAfterSec?: number;
    };

const SOS_HOURLY_LIMIT = 5;
const ONE_HOUR_MS = 60 * 60 * 1000;

async function dispatchContact(
  transport: WhatsAppTransport,
  text: string,
  contact: SosContactResult,
  clientId: string,
  memoryStore: SosMemoryStore,
): Promise<void> {
  if (contact.status === "opted_out") return;
  try {
    const messageId = await transport.send(text, contact.phone);
    memoryStore.updateMessageId(clientId, contact.phone, messageId);
  } catch {
    memoryStore.updateContactStatus(clientId, contact.phone, "failed");
  }
}

export async function handleSos(params: SosServiceParams): Promise<SosServiceResult> {
  const { installId, clientId, kind, tCrash, lat, lon, db, memoryStore, transport, limiter, logger, now, tz } =
    params;

  const existing = memoryStore.getByInstallAndClient(installId, clientId);
  if (existing) {
    return {
      ok: true,
      clientId,
      results: existing.results.map((r) => ({ phone_last4: r.phone_last4, status: r.status })),
    };
  }

  const install = getInstall(db, installId);
  if (!install) {
    return { ok: false, status: 404, error: "not_registered" };
  }

  const limitCheck = limiter.check(installId, SOS_HOURLY_LIMIT, ONE_HOUR_MS);
  if (!limitCheck.allowed) {
    return {
      ok: false,
      status: 429,
      error: "rate_limited",
      retryAfterSec: limitCheck.retryAfterSec,
    };
  }

  const registeredContacts = getContacts(db, installId);
  const text = buildSosMessage({ kind, driverName: install.driver_name, tCrash, lat, lon, tz });

  const initialResults: SosContactResult[] = registeredContacts.map((c) => ({
    phone: c.phone,
    phone_last4: c.phone.slice(-4),
    status: isOptedOut(db, c.phone) || c.status === "opted_out" ? "opted_out" : "queued",
  }));

  memoryStore.save({ clientId, installId, createdAt: now, results: initialResults });

  await Promise.allSettled(
    initialResults.map((c) => dispatchContact(transport, text, c, clientId, memoryStore)),
  );

  const updated = memoryStore.get(clientId);
  logger.info("sos_dispatched", {
    install_id: installId.slice(0, 8),
    recipients_count: initialResults.length,
  });

  return {
    ok: true,
    clientId,
    results: (updated ?? { results: initialResults }).results.map((r) => ({
      phone_last4: r.phone_last4,
      status: r.status,
    })),
  };
}
