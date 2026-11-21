import { nextOptInStatus, type OptInStatus } from "../domain/statusRank.ts";
import type { ReceiptStatus } from "../transport/WhatsAppTransport.ts";
import type { DatabaseSync } from "node:sqlite";

export interface InstallRecord {
  install_id: string;
  driver_name: string;
  created_at: number;
}

export interface ContactRecord {
  install_id: string;
  phone: string;
  name: string;
  opt_in_message_id: string | null;
  status: string;
}

export function initDb(db: DatabaseSync): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS installs (
      install_id TEXT PRIMARY KEY,
      driver_name TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS contacts (
      install_id TEXT NOT NULL,
      phone TEXT NOT NULL,
      name TEXT NOT NULL,
      opt_in_message_id TEXT,
      status TEXT NOT NULL,
      PRIMARY KEY (install_id, phone)
    );

    CREATE TABLE IF NOT EXISTS opt_outs (
      phone TEXT PRIMARY KEY
    );

    CREATE INDEX IF NOT EXISTS idx_contacts_opt_in_msg
      ON contacts(opt_in_message_id);

    CREATE INDEX IF NOT EXISTS idx_contacts_phone
      ON contacts(phone);
  `);
}

export function upsertInstall(
  db: DatabaseSync,
  installId: string,
  driverName: string,
  now: number,
): void {
  const stmt = db.prepare(`
    INSERT INTO installs (install_id, driver_name, created_at)
    VALUES (?, ?, ?)
    ON CONFLICT(install_id) DO UPDATE SET driver_name = excluded.driver_name
  `);
  stmt.run(installId, driverName, now);
}

export function getInstall(db: DatabaseSync, installId: string): InstallRecord | null {
  const stmt = db.prepare(`
    SELECT install_id, driver_name, created_at FROM installs WHERE install_id = ?
  `);
  const row = stmt.get(installId);
  return (row as InstallRecord | undefined) ?? null;
}

export function deleteInstall(db: DatabaseSync, installId: string): void {
  db.prepare("DELETE FROM contacts WHERE install_id = ?").run(installId);
  db.prepare("DELETE FROM installs WHERE install_id = ?").run(installId);
}

export function getContacts(db: DatabaseSync, installId: string): ContactRecord[] {
  const stmt = db.prepare(`
    SELECT install_id, phone, name, opt_in_message_id, status
    FROM contacts
    WHERE install_id = ?
  `);
  return stmt.all(installId) as unknown as ContactRecord[];
}

export function replaceContacts(
  db: DatabaseSync,
  installId: string,
  contacts: ContactRecord[],
): void {
  db.prepare("DELETE FROM contacts WHERE install_id = ?").run(installId);
  const insert = db.prepare(`
    INSERT INTO contacts (install_id, phone, name, opt_in_message_id, status)
    VALUES (?, ?, ?, ?, ?)
  `);
  for (const c of contacts) {
    insert.run(installId, c.phone, c.name, c.opt_in_message_id, c.status);
  }
}

export function updateContactStatusByOptInMessageId(
  db: DatabaseSync,
  messageId: string,
  receiptStatus: ReceiptStatus,
): void {
  const rows = db
    .prepare("SELECT install_id, phone, status FROM contacts WHERE opt_in_message_id = ?")
    .all(messageId) as { install_id: string; phone: string; status: OptInStatus }[];
  const upd = db.prepare("UPDATE contacts SET status = ? WHERE install_id = ? AND phone = ?");
  for (const r of rows) {
    upd.run(nextOptInStatus(r.status, receiptStatus), r.install_id, r.phone);
  }
}

export function isOptedOut(db: DatabaseSync, phone: string): boolean {
  const stmt = db.prepare("SELECT 1 FROM opt_outs WHERE phone = ?");
  return Boolean(stmt.get(phone));
}

export function recordOptOut(db: DatabaseSync, phone: string): void {
  db.prepare("INSERT OR IGNORE INTO opt_outs (phone) VALUES (?)").run(phone);
  db.prepare("UPDATE contacts SET status = 'opted_out' WHERE phone = ?").run(phone);
}
