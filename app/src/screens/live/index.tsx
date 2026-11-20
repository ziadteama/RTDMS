import { useIsFocused } from 'expo-router';
import { useKeepAwake } from 'expo-keep-awake';
import { View } from 'react-native';
import { useShallow } from 'zustand/react/shallow';

import { Banner } from '@/components/banner';
import { LiveView } from '@/components/live-view';
import { Metric } from '@/components/metric';
import { Screen } from '@/components/screen';
import { StateIndicator } from '@/components/state-indicator';
import { Text } from '@/components/text';
import { translateReason, useT, type StringKey } from '@/i18n';
import { driverState } from '@/pi/alert';
import { pi } from '@/services/pi';
import { useLive } from '@/state/live';
import { useSettings } from '@/state/settings';
import { radius, spacing, useTheme } from '@/theme';

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
  return (
    <>
      {paused ? <Banner icon="pause" title={t('banner.paused')} /> : null}
      {demo ? <Banner icon="play" title={t('banner.demo')} /> : null}
      {offline && !paused ? <Banner icon="wifiOff" tone="danger" title={t('banner.offline')} detail={t('banner.offlineHint')} /> : null}
      {noAlertApi ? <Banner icon="info" tone="warning" title={t('banner.noAlertApi')} /> : null}
    </>
  );
}

function State({ size }: { size: 'compact' | 'full' }) {
  const t = useT();
  const paused = useSettings((s) => s.paused);
  const state = useDriverState();
  const pattern = useLive((s) => s.alert?.pattern ?? null);
  const reasons = useLive(useShallow((s) => s.alert?.reasons ?? EMPTY));
  const calMessage = useLive((s) => (s.status?.drowsiness && !s.status.drowsiness.calibrated ? s.status.drowsiness.message : null));
  const lang = useSettings((s) => s.language);
  const detail = reasons.length ? reasons.map((r) => translateReason(lang, r)).join(' · ') : calMessage ? t('live.calibrate') : undefined;
  return <StateIndicator state={paused ? 'paused' : state} pattern={paused ? null : pattern} size={size} detail={detail} />;
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={{ gap: spacing.sm }}>
      <Text variant="label" tone="secondary" accessibilityRole="header" style={{ paddingHorizontal: spacing.lg }}>
        {title}
      </Text>
      <View style={{ backgroundColor: colors.surface, borderRadius: radius.md, borderCurve: 'continuous', padding: spacing.lg, flexDirection: 'row', flexWrap: 'wrap', rowGap: spacing.lg, columnGap: spacing.xl }}>
        {children}
      </View>
    </View>
  );
}

function Eyes() {
  const t = useT();
  const d = useLive(
    useShallow((s) => {
      const z = s.status?.drowsiness;
      return {
        on: !!z,
        openness: z?.openness ?? null,
        perclos: z?.perclos ?? null,
        valid: z?.perclos_valid ?? false,
        blinks: z?.blink_rate ?? null,
        closure: z ? z.closure_ms : null,
      };
    }),
  );
  if (!d.on) return null;
  return (
    <Group title={t('live.eyes')}>
      <Metric label={t('live.openness')} value={d.openness === null ? null : Math.round(d.openness * 100)} unit="%" />
      <Metric
        label={t('live.perclos')}
        value={d.perclos === null ? null : Math.round(d.perclos * 100)}
        unit="%"
        note={d.perclos !== null && !d.valid ? t('live.perclosWarming') : undefined}
      />
      <Metric label={t('live.blinks')} value={d.blinks} unit={t('live.perMin')} />
      <Metric label={t('live.closure')} value={d.closure === null ? null : (d.closure / 1000).toFixed(1)} unit={t('live.s')} />
    </Group>
  );
}

function Heart() {
  const t = useT();
  const { colors } = useTheme();
  const p = useLive(
    useShallow((s) => ({
      supported: s.physioSupported,
      watch: s.physio?.watch_connected ?? false,
      hr: s.physio?.hr_bpm ?? null,
      rr: s.physio?.rr_ms.at(-1) ?? null,
      quality: s.physio?.hrv?.quality ?? null,
      hrvState: s.physio?.hrv?.state ?? null,
      fatigue: s.physio?.fatigue_probability ?? null,
    })),
  );
  if (p.supported === false) return null;
  const qualityKey: StringKey | null =
    p.hrvState === 'warmup' ? 'quality.warmup' : p.hrvState === 'stale' ? 'quality.stale' : p.quality ? (`quality.${p.quality}` as StringKey) : null;
  const qualityColor = p.quality === 'good' ? colors.alert.none : p.quality === 'degraded' ? colors.alert.short_beep : p.quality === 'bad' ? colors.alert.continuous : undefined;
  return (
    <Group title={t('live.heart')}>
      {!p.watch ? (
        <Text tone="tertiary">{t('live.watchOff')}</Text>
      ) : (
        <>
          <Metric label={t('live.hr')} value={p.hr} unit={t('live.bpm')} />
          <Metric label={t('live.rr')} value={p.rr} unit={t('live.ms')} />
          <Metric label={t('live.quality')} value={qualityKey ? t(qualityKey) : null} color={qualityColor} />
          <Metric label={t('live.fatigue')} value={p.fatigue === null ? null : Math.round(p.fatigue * 100)} unit="%" />
        </>
      )}
    </Group>
  );
}

function Phone() {
  const t = useT();
  const { colors } = useTheme();
  const h = useLive(useShallow((s) => ({ on: !!s.status?.hybrid, call: s.status?.hybrid?.call ?? false, texting: s.status?.hybrid?.texting ?? false })));
  if (!h.on) return null;
  return (
    <Group title={t('live.phone')}>
      <Metric label={t('live.call')} value={h.call ? t('live.detected') : t('live.none')} color={h.call ? colors.alert.continuous : undefined} />
      <Metric label={t('live.texting')} value={h.texting ? t('live.detected') : t('live.none')} color={h.texting ? colors.alert.continuous : undefined} />
    </Group>
  );
}

function Speed() {
  const t = useT();
  const units = useSettings((s) => s.units);
  const kmh = useLive((s) => (s.speedKmh === null ? null : Math.round(s.speedKmh)));
  if (kmh === null) return null;
  const v = units === 'mph' ? Math.round(kmh * KMH_TO_MPH) : kmh;
  return (
    <Text variant="metricSmall" tone="secondary" align="center">
      {t('live.speed', { v, u: t(units === 'mph' ? 'common.mph' : 'common.kmh') })}
    </Text>
  );
}

function Video() {
  const t = useT();
  const online = useLive((s) => s.connection === 'online');
  const demo = useSettings((s) => s.demo);
  const focused = useIsFocused();
  // Unmounted when not visible: stream.py only encodes JPEGs while someone is watching.
  const url = online && focused && !demo ? pi().streamUrl() : null;
  return <LiveView url={url} emptyLabel={t('live.noVideo')} />;
}

export function Live() {
  useKeepAwake();
  const t = useT();
  const locked = useDrivingLock();
  if (locked)
    return (
      <View style={{ flex: 1, padding: spacing.lg, gap: spacing.lg }}>
        <Banners />
        <State size="full" />
        <Speed />
        <Text variant="caption" tone="tertiary" align="center">
          {t('live.locked')}
        </Text>
      </View>
    );
  return (
    <Screen>
      <Banners />
      <State size="compact" />
      <Video />
      <Eyes />
      <Heart />
      <Phone />
    </Screen>
  );
}
