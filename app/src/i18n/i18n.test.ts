import { ar } from './ar';
import { en, type StringKey } from './en';
import { translateReason } from './index';

// index.ts reaches the settings store; keep SQLite (native) out of this Node test.
jest.mock('@/state/storage', () => {
  const m = new Map<string, string>();
  return { kv: { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) }, clearKv: () => m.clear() };
});

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe('translations', () => {
  it('Arabic has every key, none empty', () => {
    for (const k of Object.keys(en) as StringKey[]) expect(ar[k]?.trim()).toBeTruthy();
  });

  it('Arabic keeps the same {placeholders} as English', () => {
    for (const k of Object.keys(en) as StringKey[]) expect([k, placeholders(ar[k])]).toEqual([k, placeholders(en[k])]);
  });

  it('translates known fusion reasons and passes unknown ones through', () => {
    expect(translateReason('ar', 'face drowsy')).toBe('وجه نعسان');
    expect(translateReason('ar', 'new fusion reason')).toBe('new fusion reason');
  });
});
