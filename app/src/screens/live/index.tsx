import { useKeepAwake } from 'expo-keep-awake';
import { useEffect, useState } from 'react';
import { View } from 'react-native';
import { useShallow } from 'zustand/react/shallow';

import { Banner } from '@/components/banner';
import { Dot } from '@/components/dot';
import { HoldButton } from '@/components/hold-button';
import { Screen } from '@/components/screen';
import { StateIndicator } from '@/components/state-indicator';
import { Text } from '@/components/text';
import { translateReason, useT } from '@/i18n';
import { driverState } from '@/pi/alert';
import { triggerSos } from '@/services/emergency';
import { gpsLost } from '@/services/monitor';
import { db } from '@/state/db';
import { useLive } from '@/state/live';
import { useSettings } from '@/state/settings';
import { radius, spacing, useTheme } from '@/theme';
import { formatDuration } from '@/utils/format';

import { LastTrip } from './last-trip';
import { useDrivingLock } from './use-driving-lock';

const EMPTY: string[] = [];
const KMH_TO_MPH = 0.621371;

function useDriverState() {
  return useLive((s) => driverState(s.status, s.connection === 'online'));
}

function Banners() {
  const t = useT();
  const { demo, paused } = useSettings(useShallow((s) => ({ demo: s.demo, paused: s.paused })));
  const offline = useLive((s) => s.connection === 'offline');
  const noAlertApi = useLive((s) => s.connection === 'online' && s.alertSupported === false);
  const noGps = useLive((s) => s.connection === 'online' && gpsLost(s.gpsAt, Date.now()));
  const crashOn = useSettings((s) => s.crashDetection);

  return (
    <>
      {paused ? <Banner icon="pause" title={t('banner.paused')} /> : null}
      {demo ? <Banner icon="play" title={t('banner.demo')} /> : null}
      {offline && !paused ? <Banner icon="wifiOff" tone="danger" title={t('banner.offline')} detail={t('banner.offlineHint')} /> : null}
      {noAlertApi ? <Banner icon="info" tone="warning" title={t('banner.noAlertApi')} /> : null}
      {noGps && crashOn ? <Banner icon="gps" tone="warning" title={t('banner.gpsLost')} /> : null}
    </>
  );
}

function StatusPill() {
  const t = useT();
  const { colors } = useTheme();
  const online = useLive((s) => s.connection === 'online');
  const paused = useSettings((s) => s.paused);
  const demo = useSettings((s) => s.demo);

  if (!online || paused || demo) return null;

  return (
    <View
      style={{
        alignSelf: 'center',
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.xs,
        borderRadius: radius.full,
        backgroundColor: colors.surfaceRaised,
      }}
    >
      <Dot color={colors.alert.none} />
      <Text variant="caption" tone="secondary">
        {t('live.statusPill')}
      </Text>
    </View>
  );
}

function State({ size }: { size: 'compact' | 'full' }) {
  const t = useT();
  const paused = useSettings((s) => s.paused);
  const state = useDriverState();
  const pattern = useLive((s) => s.alert?.pattern ?? null);
  const reasons = useLive(useShallow((s) => s.alert?.reasons ?? EMPTY));
  const calMessage = useLive((s) => (s.status?.drowsiness && !s.status.drowsiness.calibrated ? s.status.drowsiness.message : null));
  const detail = reasons.length ? reasons.map((r) => translateReason(r)).join(' · ') : calMessage ? t('live.calibrate') : undefined;

  return <StateIndicator state={paused ? 'paused' : state} pattern={paused ? null : pattern} size={size} detail={detail} />;
}

function useNow(intervalMs = 5000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function ContextLine() {
  const t = useT();
  const units = useSettings((s) => s.units);
  const kmh = useLive((s) => (s.speedKmh === null ? null : Math.round(s.speedKmh)));
  const open = db.openTrip();
  const startedAt = open ? open.startedAt : null;
  const now = useNow();
  const durationMs = startedAt !== null ? Math.max(0, now - startedAt) : null;

  if (kmh === null && durationMs === null) return null;

  const speedVal = kmh !== null ? (units === 'mph' ? Math.round(kmh * KMH_TO_MPH) : kmh) : 0;
  const speedStr = kmh !== null ? t('live.speed', { v: speedVal, u: t(units === 'mph' ? 'common.mph' : 'common.kmh') }) : '';
  const timeStr = durationMs !== null ? formatDuration(durationMs, { h: t('common.h'), min: t('common.min'), s: t('live.s') }) : '';

  const text = speedStr && timeStr ? t('live.context', { speed: speedStr, time: timeStr }) : speedStr || timeStr;

  return (
    <Text variant="metricSmall" tone="secondary" align="center">
      {text}
    </Text>
  );
}

function Sos() {
  const t = useT();
  return <HoldButton label={t('live.sos')} hint={t('live.sosHint')} onComplete={() => triggerSos('manual')} />;
}

export function Live() {
  useKeepAwake();
  const t = useT();
  const locked = useDrivingLock();

  if (locked) {
    return (
      <View style={{ flex: 1, padding: spacing.lg, gap: spacing.lg }}>
        <Banners />
        <StatusPill />
        <State size="full" />
        <ContextLine />
        <Text variant="caption" tone="tertiary" align="center">
          {t('live.locked')}
        </Text>
        <Sos />
      </View>
    );
  }

  return (
    <Screen contentContainerStyle={{ flexGrow: 1 }}>
      <Banners />
      <StatusPill />
      <State size="full" />
      <ContextLine />
      <Sos />
      <LastTrip />
    </Screen>
  );
}
