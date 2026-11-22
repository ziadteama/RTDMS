export type SosMessageKind = 'crash' | 'manual' | 'unresponsive';

export type SosMessageParams = {
  kind: SosMessageKind;
  date?: Date;
  lat?: number | null;
  lon?: number | null;
};

/** Formats a date into {hh:mm} {AM/PM} (e.g. "12:59 PM", "09:05 AM") */
export function formatTimeAmPm(date: Date = new Date()): string {
  const hoursRaw = date.getHours();
  const minutes = date.getMinutes().toString().padStart(2, '0');
  const ampm = hoursRaw >= 12 ? 'PM' : 'AM';
  const hours12 = hoursRaw % 12 || 12;
  const hours = hours12.toString().padStart(2, '0');
  return `${hours}:${minutes} ${ampm}`;
}

/**
 * Pure builder function for link-free SOS SMS text.
 * Strictly ASCII, GSM-7 charset compatible, length <= 160 chars.
 *
 * Crash with loc:  SAHI crash alert {hh:mm} {AM/PM}. The driver may need help. Location (paste in Maps): {lat},{lon}
 * Crash no loc:    SAHI crash alert {hh:mm} {AM/PM}. The driver may need help. Location unknown.
 * Manual with loc: SAHI alert {hh:mm} {AM/PM}. The driver may need help. Location (paste in Maps): {lat},{lon}
 * Manual no loc:   SAHI alert {hh:mm} {AM/PM}. The driver may need help. Location unknown.
 */
export function buildSosSms(params: SosMessageParams): string {
  const time = formatTimeAmPm(params.date);
  const prefix = params.kind === 'crash' ? `SAHI crash alert ${time}` : `SAHI alert ${time}`;
  const message = params.kind === 'unresponsive' ? 'The driver is not responding.' : 'The driver may need help.';
  const hasCoords = typeof params.lat === 'number' && typeof params.lon === 'number' &&
    Number.isFinite(params.lat) && Number.isFinite(params.lon);

  if (hasCoords) {
    const latStr = (params.lat as number).toFixed(5);
    const lonStr = (params.lon as number).toFixed(5);
    return `${prefix}. ${message} Location (paste in Maps): ${latStr},${lonStr}`;
  }

  return `${prefix}. ${message} Location unknown.`;
}
