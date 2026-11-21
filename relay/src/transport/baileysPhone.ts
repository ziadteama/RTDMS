/**
 * Pure functions for WhatsApp JID <-> E.164 phone conversions and validations.
 */

const E164_REGEX = /^\+[1-9]\d{6,14}$/;
const DIGITS_ONLY_REGEX = /^\d{7,15}$/;
const S_WHATSAPP_NET = "@s.whatsapp.net";
const LID_SUFFIX = "@lid";

/**
 * Converts an E.164 phone number (e.g. "+201000000001") to a WhatsApp user JID.
 * Returns null if the input is not a valid E.164 format.
 */
export function e164ToJid(e164: string): string | null {
  if (!E164_REGEX.test(e164)) {
    return null;
  }
  const digits = e164.slice(1);
  return `${digits}${S_WHATSAPP_NET}`;
}

/**
 * Converts a WhatsApp user JID (e.g. "201000000001@s.whatsapp.net" or "201000000001:1@s.whatsapp.net")
 * to an E.164 phone number ("+201000000001").
 * Returns null for non-user JIDs (e.g. groups, broadcasts, LIDs) or invalid formats.
 */
export function jidToE164(jid: string): string | null {
  if (!isUserJid(jid)) {
    return null;
  }
  const atIndex = jid.indexOf("@");
  if (atIndex === -1) {
    return null;
  }
  const userPart = jid.slice(0, atIndex);
  const colonIndex = userPart.indexOf(":");
  const phoneDigits = colonIndex === -1 ? userPart : userPart.slice(0, colonIndex);
  if (!DIGITS_ONLY_REGEX.test(phoneDigits)) {
    return null;
  }
  return `+${phoneDigits}`;
}

/**
 * Returns true if the JID is an internal WhatsApp LID (Linked Identity Device) address.
 */
export function isLidJid(jid: string): boolean {
  return jid.endsWith(LID_SUFFIX);
}

/**
 * Returns true if the JID is a standard 1:1 user WhatsApp chat.
 */
export function isUserJid(jid: string): boolean {
  return jid.endsWith(S_WHATSAPP_NET);
}
