import { en, type StringKey } from './en';

export type { StringKey } from './en';

export function t(key: StringKey, params?: Record<string, string | number>): string {
  let s: string = en[key];
  if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}

/** English fusion reason; unknown reasons are shown as sent. */
export function translateReason(reason: string): string {
  const key = `reason.${reason}` as StringKey;
  return key in en ? t(key) : reason;
}

export function useT() {
  return t;
}
