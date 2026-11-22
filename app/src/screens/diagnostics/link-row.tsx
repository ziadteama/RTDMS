import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

import { Row } from '@/components/list';
import { dx } from '@/i18n/diagnostics';
import { getBleLink } from '@/pi/ble';
import { useLive } from '@/state/live';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';

const RSSI_MS = 5000;

/**
 * Link, signal strength and age of the last update, for the hidden Diagnostics screen. The two
 * timers (1 s clock, 5 s signal read) only run while the screen is focused and are cleared on
 * blur or unmount; the signal is read only while the Bluetooth link is online.
 */
export function useLinkRows() {
  const link = useLive((s) => s.link);
  const paired = useSettings((s) => !!s.bleName);
  const hasToken = useSecure((s) => !!s.piToken);
  const openLink = paired && !hasToken;
  const [rssi, setRssi] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useFocusEffect(
    useCallback(() => {
      const ble = getBleLink();
      const readRssi = () => {
        if (ble.state !== 'online') return setRssi(null);
        ble.readRssi().then(setRssi, () => setRssi(null));
      };
      readRssi();
      const clock = setInterval(() => setNow(Date.now()), 1000);
      const signal = setInterval(readRssi, RSSI_MS);
      return () => {
        clearInterval(clock);
        clearInterval(signal);
      };
    }, []),
  );

  const last = getBleLink().lastNotifyAt;
  const unknown = dx('diag.link.unknown');
  const linkLabel = link === 'ble' ? dx(openLink ? 'diag.link.open' : 'diag.link.ble') : link === 'http' ? dx('diag.link.http') : dx('diag.link.none');
  return [
    <Row key="link" label={dx('diag.link.label')} icon="bluetooth" value={linkLabel} accessibilityRole="text" />,
    <Row
      key="signal"
      label={dx('diag.link.signal')}
      value={link === 'ble' && rssi !== null ? dx('diag.link.dbm', { dbm: rssi }) : unknown}
      accessibilityRole="text"
    />,
    <Row
      key="last"
      label={dx('diag.link.last')}
      value={last === null ? unknown : dx('diag.link.ago', { s: (Math.max(0, now - last) / 1000).toFixed(1) })}
      accessibilityRole="text"
    />,
  ];
}
