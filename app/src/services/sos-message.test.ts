import { buildSosSms, formatTimeAmPm } from './sos-message';

// Standard GSM 7-bit default alphabet characters
const GSM7_BASIC =
  '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà';

function isGsm7(text: string): boolean {
  for (let i = 0; i < text.length; i++) {
    if (!GSM7_BASIC.includes(text[i]!)) {
      return false;
    }
  }
  return true;
}

describe('buildSosSms', () => {
  const dateAm = new Date(2026, 10, 21, 9, 5); // 09:05 AM
  const datePm = new Date(2026, 10, 21, 23, 59); // 11:59 PM

  it('formats crash variant with location with exactly 5 decimals', () => {
    const text = buildSosSms({
      kind: 'crash',
      date: dateAm,
      lat: 30.044421,
      lon: 31.235712,
    });
    expect(text).toBe('SAHI crash alert 09:05 AM. The driver may need help. Location (paste in Maps): 30.04442,31.23571');
    expect(isGsm7(text)).toBe(true);
    expect(text.length).toBeLessThanOrEqual(160);
  });

  it('formats crash variant without location', () => {
    const text = buildSosSms({
      kind: 'crash',
      date: datePm,
      lat: null,
      lon: null,
    });
    expect(text).toBe('SAHI crash alert 11:59 PM. The driver may need help. Location unknown.');
    expect(isGsm7(text)).toBe(true);
    expect(text.length).toBeLessThanOrEqual(160);
  });

  it('formats manual variant with location (no "crash")', () => {
    const text = buildSosSms({
      kind: 'manual',
      date: dateAm,
      lat: 30.04440,
      lon: 31.23570,
    });
    expect(text).toBe('SAHI alert 09:05 AM. The driver may need help. Location (paste in Maps): 30.04440,31.23570');
    expect(isGsm7(text)).toBe(true);
    expect(text.length).toBeLessThanOrEqual(160);
  });

  it('formats manual variant without location (no "crash")', () => {
    const text = buildSosSms({
      kind: 'manual',
      date: datePm,
    });
    expect(text).toBe('SAHI alert 11:59 PM. The driver may need help. Location unknown.');
    expect(isGsm7(text)).toBe(true);
    expect(text.length).toBeLessThanOrEqual(160);
  });

  it('asserts GSM-7 charset and length <= 160 for worst-case values (negative coordinates, 12-hour midnight)', () => {
    const worstCaseDate = new Date(2026, 10, 21, 12, 59); // 12:59 PM
    const text = buildSosSms({
      kind: 'crash',
      date: worstCaseDate,
      lat: -89.99999,
      lon: -179.99999,
    });
    expect(text).toBe('SAHI crash alert 12:59 PM. The driver may need help. Location (paste in Maps): -89.99999,-179.99999');
    expect(isGsm7(text)).toBe(true);
    expect(text.length).toBeLessThanOrEqual(160);
    // Ensure no URL in text
    expect(text).not.toContain('http://');
    expect(text).not.toContain('https://');
    // Ensure no "Automatic message"
    expect(text).not.toContain('Automatic message');
  });

  it('formatTimeAmPm formats hours with leading zeros for single digits', () => {
    expect(formatTimeAmPm(new Date(2026, 10, 21, 0, 0))).toBe('12:00 AM');
    expect(formatTimeAmPm(new Date(2026, 10, 21, 12, 0))).toBe('12:00 PM');
    expect(formatTimeAmPm(new Date(2026, 10, 21, 7, 9))).toBe('07:09 AM');
  });
});
