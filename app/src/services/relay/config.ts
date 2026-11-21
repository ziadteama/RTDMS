import Constants from 'expo-constants';
import { useSettings } from '@/state/settings';

export type RelayConfig = {
  baseUrl: string;
  apiKey: string;
};

/**
 * Returns relay URL and key from settings store override, or build config (process.env / extra).
 * Never print, log, or commit keys/URLs.
 */
export function getRelayConfig(): RelayConfig | null {
  const settings = useSettings.getState();
  const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, unknown>;

  const rawUrl =
    settings.relayUrl?.trim() ||
    process.env.EXPO_PUBLIC_RELAY_URL?.trim() ||
    (typeof extra.relayUrl === 'string' ? extra.relayUrl.trim() : '');

  const rawKey =
    settings.relayKey?.trim() ||
    process.env.EXPO_PUBLIC_RELAY_KEY?.trim() ||
    (typeof extra.relayKey === 'string' ? extra.relayKey.trim() : '');

  if (!rawUrl || !rawKey) return null;

  return {
    baseUrl: rawUrl.replace(/\/+$/, ''),
    apiKey: rawKey,
  };
}
