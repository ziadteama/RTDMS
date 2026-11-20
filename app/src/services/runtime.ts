import { useEffect } from 'react';

import { applyDirection } from '@/i18n';
import { useSettings } from '@/state/settings';

import { startAlertEngine } from './alerts';
import { startPoller } from './poller';

/**
 * Starts the background services once the driver has consented and finished onboarding, and
 * stops all of them while monitoring is paused. Restarts them when the Pi source changes.
 */
export function useRuntime(): void {
  const onboarded = useSettings((s) => s.onboarded);
  const paused = useSettings((s) => s.paused);
  const demo = useSettings((s) => s.demo);
  const baseUrl = useSettings((s) => s.baseUrl);
  const language = useSettings((s) => s.language);

  useEffect(() => applyDirection(language, true), [language]);

  useEffect(() => {
    if (!onboarded || paused) return;
    const stops = [startPoller(), startAlertEngine()];
    return () => stops.forEach((stop) => stop());
  }, [onboarded, paused, demo, baseUrl]);
}
