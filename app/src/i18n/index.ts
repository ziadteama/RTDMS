import { getLocales } from 'expo-localization';
import { I18nManager, Platform } from 'react-native';
import { reloadAppAsync } from 'expo';

import { useSettings, type Language } from '@/state/settings';

import { ar } from './ar';
import { en, type StringKey } from './en';

export type { StringKey } from './en';

const DICTS: Record<Language, Record<StringKey, string>> = { en, ar };

/** Speech locales for expo-speech (voice depends on installed TTS voices). */
export const SPEECH_LOCALE: Record<Language, string> = { en: 'en-US', ar: 'ar-EG' };

export function translate(lang: Language, key: StringKey, params?: Record<string, string | number>): string {
  let s = DICTS[lang][key] ?? en[key];
  if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}

/** A fusion reason in the app language; reasons this build does not know are shown as sent. */
export function translateReason(lang: Language, reason: string): string {
  const key = `reason.${reason}` as StringKey;
  return key in en ? translate(lang, key) : reason;
}

/** Layout direction now (web: the document direction the app set). */
export function isRTL(): boolean {
  if (Platform.OS === 'web') return typeof document !== 'undefined' && document.documentElement.dir === 'rtl';
  return I18nManager.isRTL;
}

/** Hook: re-renders only when the language changes. */
export function useT() {
  const lang = useSettings((s) => s.language);
  return (key: StringKey, params?: Record<string, string | number>) => translate(lang, key, params);
}

/** For non-React code (services). */
export const t = (key: StringKey, params?: Record<string, string | number>) =>
  translate(useSettings.getState().language, key, params);

export function deviceLanguage(): Language {
  return getLocales()[0]?.languageCode === 'ar' ? 'ar' : 'en';
}

/**
 * Real RTL: React Native mirrors layouts natively, which on Android only takes effect after a
 * reload. Web (screenshots) flips the document direction instead.
 */
export function applyDirection(lang: Language, reloadIfNeeded: boolean): void {
  const rtl = lang === 'ar';
  if (Platform.OS === 'web') {
    if (typeof document !== 'undefined') {
      document.documentElement.dir = rtl ? 'rtl' : 'ltr';
      document.documentElement.lang = lang;
    }
    return;
  }
  I18nManager.allowRTL(true);
  if (I18nManager.isRTL !== rtl) {
    I18nManager.forceRTL(rtl);
    if (reloadIfNeeded) void reloadAppAsync('language direction changed');
  }
}
