import type { DatabaseSync } from "node:sqlite";
import type { WhatsAppTransport } from "../transport/WhatsAppTransport.ts";
import type { Logger } from "../log/Logger.ts";
import {
  upsertInstall,
  getContacts,
  replaceContacts,
  isOptedOut,
  type ContactRecord,
} from "../store/db.ts";
import { buildOptInMessage } from "../domain/messages.ts";
import type { ValidContact } from "../domain/validate.ts";

export interface RegisterResultItem {
  phone_last4: string;
  status: string;
}

export interface RegisterServiceParams {
  installId: string;
  driverName: string;
  contacts: ValidContact[];
  db: DatabaseSync;
  transport: WhatsAppTransport;
  logger: Logger;
  now: number;
}

interface ProcessedContact {
  record: ContactRecord;
  sendNeeded: boolean;
}

async function sendOptIn(
  transport: WhatsAppTransport,
  text: string,
  phone: string,
): Promise<{ status: string; optInMessageId: string | null }> {
  try {
    const msgId = await transport.send(text, phone);
    return { status: "pending", optInMessageId: msgId };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (message.includes("not_on_whatsapp")) {
      return { status: "invalid", optInMessageId: null };
    }
    return { status: "failed", optInMessageId: null };
  }
}

function classifyContact(
  contact: ValidContact,
  existingByPhone: Map<string, ContactRecord>,
  installId: string,
  optedOut: boolean,
): ProcessedContact {
  if (optedOut) {
    return {
      record: {
        install_id: installId,
        phone: contact.phone,
        name: contact.name,
        opt_in_message_id: null,
        status: "opted_out",
      },
      sendNeeded: false,
    };
  }

  const existing = existingByPhone.get(contact.phone);
  if (existing) {
    return {
      record: {
        install_id: installId,
        phone: contact.phone,
        name: contact.name,
        opt_in_message_id: existing.opt_in_message_id,
        status: existing.status,
      },
      sendNeeded: false,
    };
  }

  return {
    record: {
      install_id: installId,
      phone: contact.phone,
      name: contact.name,
      opt_in_message_id: null,
      status: "pending",
    },
    sendNeeded: true,
  };
}

export async function handleRegister(
  params: RegisterServiceParams,
): Promise<{ contacts: RegisterResultItem[] }> {
  const { installId, driverName, contacts, db, transport, logger, now } = params;

  upsertInstall(db, installId, driverName, now);
  const existingList = getContacts(db, installId);
  const existingByPhone = new Map(existingList.map((c) => [c.phone, c]));

  const optInText = buildOptInMessage(driverName);
  const classified = contacts.map((c) =>
    classifyContact(c, existingByPhone, installId, isOptedOut(db, c.phone)),
  );

  const finalRecords: ContactRecord[] = await Promise.all(
    classified.map(async ({ record, sendNeeded }) => {
      if (!sendNeeded) return record;
      const sendResult = await sendOptIn(transport, optInText, record.phone);
      return {
        ...record,
        status: sendResult.status,
        opt_in_message_id: sendResult.optInMessageId,
      };
    }),
  );

  replaceContacts(db, installId, finalRecords);
  logger.info("register_completed", {
    install_id: installId.slice(0, 8),
    contacts_count: finalRecords.length,
  });

  return {
    contacts: finalRecords.map((r) => ({
      phone_last4: r.phone.slice(-4),
      status: r.status,
    })),
  };
}
