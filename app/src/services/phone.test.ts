import { isValidPhone, normalizeE164 } from './phone';

describe('normalizeE164', () => {
  it('normalizes local Egyptian mobile numbers (010, 011, 012, 015)', () => {
    expect(normalizeE164('01001234567')).toBe('+201001234567');
    expect(normalizeE164('01112345678')).toBe('+201112345678');
    expect(normalizeE164('01223456789')).toBe('+201223456789');
    expect(normalizeE164('01556789012')).toBe('+201556789012');
  });

  it('preserves existing E.164 numbers with +', () => {
    expect(normalizeE164('+201001234567')).toBe('+201001234567');
    expect(normalizeE164('+14155552671')).toBe('+14155552671');
  });

  it('converts leading 00 to +', () => {
    expect(normalizeE164('00201001234567')).toBe('+201001234567');
  });

  it('strips formatting spaces, dashes and parentheses', () => {
    expect(normalizeE164('+20 100-123-4567')).toBe('+201001234567');
    expect(normalizeE164('(010) 0123 4567')).toBe('+201001234567');
  });

  it('validates E.164 pattern', () => {
    expect(isValidPhone('+201001234567')).toBe(true);
    expect(isValidPhone('+14155552671')).toBe(true);
    expect(isValidPhone('01001234567')).toBe(false);
    expect(isValidPhone('+1')).toBe(false);
  });
});
