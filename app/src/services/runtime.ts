import { useEffect } from 'react';
import { I18nManager } from 'react-native';

import { seedDemoHistory } from '@/demo/seed';
import { db } from '@/state/db';
import { useSettings } from '@/state/settings';

import { startAlertEngine } from './alerts';
import { startMonitor } from './monitor';
import { startPoller } from './poller';
import { startTripManager } from './trips';

/**
 * Starts the background services once the driver has consented and finished onboarding, and
 * stops all of them while monitoring is paused. Restarts them when the Pi source changes.
 */
export function useRuntime(): void {
  const onboarded = useSettings((s) => s.onboarded);
  const paused = useSettings((s) => s.paused);
  const demo = useSettings((s) => s.demo);
  const baseUrl = useSettings((s) => s.baseUrl);

  useEffect(() => {
    // English only: clear any RTL preference an earlier build persisted natively.
    if (I18nManager.isRTL) {
      I18nManager.allowRTL(false);
      I18nManager.forceRTL(false);
    }
  }, []);

  useEffect(() => {
    if (demo) seedDemoHistory();
    else db.deleteDemo();
  }, [demo]);

  useEffect(() => {
    if (!onboarded || paused) return;
    const stops = [startPoller(), startTripManager(), startAlertEngine(), startMonitor()];
    return () => stops.forEach((stop) => stop());
  }, [onboarded, paused, demo, baseUrl]);
}
