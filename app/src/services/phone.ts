/**
 * Phone number normalization to E.164 standard (+201001234567).
 * Pure function: strips non-digits (keeping leading +), converts 00 prefix,
 * and formats Egyptian local mobile numbers (010, 011, 012, 015).
 */
export function normalizeE164(raw: string, defaultCountry = '20'): string {
  const trimmed = raw.trim();
  if (!trimmed) return '';
  let cleaned = trimmed.replace(/^00/, '+');
  cleaned = cleaned.startsWith('+')
    ? '+' + cleaned.slice(1).replace(/\D/g, '')
    : cleaned.replace(/\D/g, '');

  if (cleaned.startsWith('+')) {
    return cleaned;
  }
  // Local Egyptian mobile (e.g. 01001234567 -> +201001234567)
  if (cleaned.startsWith('0') && cleaned.length >= 10) {
    return `+${defaultCountry}${cleaned.slice(1)}`;
  }
  return `+${defaultCountry}${cleaned}`;
}

export function isValidPhone(phone: string): boolean {
  return /^\+[1-9]\d{6,14}$/.test(phone);
}
