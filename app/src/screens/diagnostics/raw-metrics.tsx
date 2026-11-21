import { View } from 'react-native';
import { useShallow } from 'zustand/react/shallow';

import { Metric } from '@/components/metric';
import { Text } from '@/components/text';
import { dx } from '@/i18n/diagnostics';
import { useLive } from '@/state/live';
import { radius, spacing, useTheme } from '@/theme';

function MetricGroup({ title, children }: { title: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={{ gap: spacing.sm }}>
      <Text variant="label" tone="secondary" accessibilityRole="header" style={{ paddingHorizontal: spacing.lg }}>
        {title}
      </Text>
      <View
        style={{
          backgroundColor: colors.surface,
          borderRadius: radius.md,
          borderCurve: 'continuous',
          padding: spacing.lg,
          flexDirection: 'row',
          flexWrap: 'wrap',
          rowGap: spacing.lg,
          columnGap: spacing.xl,
        }}
      >
        {children}
      </View>
    </View>
  );
}

function EyesMetrics() {
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
    <MetricGroup title={dx('diag.raw.eyes')}>
      <Metric label={dx('diag.raw.openness')} value={d.openness === null ? null : Math.round(d.openness * 100)} unit="%" />
      <Metric
        label={dx('diag.raw.perclos')}
        value={d.perclos === null ? null : Math.round(d.perclos * 100)}
        unit="%"
        note={d.perclos !== null && !d.valid ? dx('diag.raw.perclosWarming') : undefined}
      />
      <Metric label={dx('diag.raw.blinks')} value={d.blinks} unit={dx('diag.raw.perMin')} />
      <Metric label={dx('diag.raw.closure')} value={d.closure === null ? null : (d.closure / 1000).toFixed(1)} unit={dx('diag.raw.s')} />
    </MetricGroup>
  );
}

function HeartMetrics() {
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
  const qualityColor =
    p.quality === 'good' ? colors.alert.none : p.quality === 'degraded' ? colors.alert.short_beep : p.quality === 'bad' ? colors.alert.continuous : undefined;

  return (
    <MetricGroup title={dx('diag.raw.heart')}>
      {!p.watch ? (
        <Text tone="tertiary">{dx('diag.raw.watchOff')}</Text>
      ) : (
        <>
          <Metric label={dx('diag.raw.hr')} value={p.hr} unit={dx('diag.raw.bpm')} />
          <Metric label={dx('diag.raw.rr')} value={p.rr} unit={dx('diag.raw.ms')} />
          <Metric label={dx('diag.raw.quality')} value={p.quality ?? p.hrvState} color={qualityColor} />
          <Metric label={dx('diag.raw.fatigue')} value={p.fatigue === null ? null : Math.round(p.fatigue * 100)} unit="%" />
        </>
      )}
    </MetricGroup>
  );
}

function PhoneMetrics() {
  const { colors } = useTheme();
  const h = useLive(useShallow((s) => ({ on: !!s.status?.hybrid, call: s.status?.hybrid?.call ?? false, texting: s.status?.hybrid?.texting ?? false })));
  if (!h.on) return null;
  return (
    <MetricGroup title={dx('diag.raw.phone')}>
      <Metric label={dx('diag.raw.call')} value={h.call ? dx('diag.raw.detected') : dx('diag.raw.none')} color={h.call ? colors.alert.continuous : undefined} />
      <Metric label={dx('diag.raw.texting')} value={h.texting ? dx('diag.raw.detected') : dx('diag.raw.none')} color={h.texting ? colors.alert.continuous : undefined} />
    </MetricGroup>
  );
}

export function RawMetrics() {
  return (
    <View style={{ gap: spacing.lg }}>
      <EyesMetrics />
      <HeartMetrics />
      <PhoneMetrics />
    </View>
  );
}
