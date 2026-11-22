import { useEffect } from 'react';
import { I18nManager } from 'react-native';

import { seedDemoHistory } from '@/demo/seed';
import { db } from '@/state/db';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';

import { startAlertEngine } from './alerts';
import { startBleLink } from './ble-link';
import { startCalibrationSync } from './calibration-sync';
import { startIncidentDelivery } from './incident-delivery';
import { startMonitor } from './monitor';
import { startPoller } from './poller';
import { syncRelayContacts } from './relay/contacts';
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
    if (onboarded) return startIncidentDelivery();
  }, [onboarded]);

  useEffect(() => {
    return startCalibrationSync();
  }, []);

  useEffect(() => {
    const { contacts, setContacts } = useSecure.getState();
    const driverName = useSettings.getState().driverName ?? 'Driver';
    if (contacts.length > 0 && contacts.some((c) => c.relayStatus === 'failed' || !c.relayStatus)) {
      void syncRelayContacts(driverName, contacts).then((synced) => {
        setContacts(synced);
      });
    }
  }, []);

  // Not gated on onboarding: pairing happens during it and the pair screen waits for the link.
  // The service watches the pairing in the stores itself (and sits idle with no timers if none).
  useEffect(() => {
    if (!paused) return startBleLink();
  }, [paused]);

  useEffect(() => {
    if (!onboarded || paused) return;
    const stops = [startPoller(), startTripManager(), startAlertEngine(), startMonitor()];
    return () => stops.forEach((stop) => stop());
  }, [onboarded, paused, demo, baseUrl]);
}
