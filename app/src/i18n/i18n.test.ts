import { en, type StringKey } from './en';
import { t, translateReason } from './index';

describe('English strings', () => {
  it.each(Object.keys(en) as StringKey[])('%s is nonempty and substitutes every placeholder', (key) => {
    const params = Object.fromEntries([...en[key].matchAll(/\{(\w+)\}/g)].map((m) => [m[1], `value-${m[1]}`]));
    const result = t(key, params);
    expect(result.trim()).toBeTruthy();
    expect(result).not.toMatch(/\{[^}]*\}/);
    for (const value of Object.values(params)) expect(result).toContain(value);
  });

  it('translates known fusion reasons and passes unknown ones through', () => {
    expect(translateReason('face drowsy')).toBe('Drowsy face');
    expect(translateReason('new fusion reason')).toBe('new fusion reason');
  });
});
