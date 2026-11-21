import { View } from 'react-native';

import { radius, spacing, useTheme } from '@/theme';

import { Text } from './text';

/**
 * Minimal bar chart built from Views (no chart library for two small charts). Bars are neutral;
 * a bar only takes a semantic color when the caller passes one (e.g. a score band).
 */
export function BarChart({
  data,
  max,
  height = 130,
  label,
}: {
  data: { key: string; value: number | null; label: string; color?: string }[];
  max: number;
  height?: number;
  label: string;
}) {
  const { colors } = useTheme();
  return (
    <View accessible accessibilityLabel={`${label}: ${data.map((d) => `${d.label} ${d.value ?? '—'}`).join(', ')}`}>
      <View style={{ height, flexDirection: 'row', alignItems: 'flex-end', gap: spacing.xs }}>
        {data.map((d) => (
          <View key={d.key} style={{ flex: 1, alignItems: 'center', gap: spacing.xs }}>
            <Text variant="caption" tone="secondary" style={{ fontVariant: ['tabular-nums'] }}>
              {d.value ?? ''}
            </Text>
            <View
              style={{
                width: '60%',
                height: d.value === null ? 2 : Math.max(4, (d.value / max) * (height - 24)),
                backgroundColor: d.value === null ? colors.separator : (d.color ?? colors.textSecondary),
                borderRadius: radius.sm / 2,
              }}
            />
          </View>
        ))}
      </View>
      <View style={{ flexDirection: 'row', gap: spacing.xs, marginTop: spacing.sm }}>
        {data.map((d) => (
          <Text key={d.key} variant="caption" tone="tertiary" style={{ flex: 1, textAlign: 'center' }} numberOfLines={1}>
            {d.label}
          </Text>
        ))}
      </View>
    </View>
  );
}

/** A thin line of points for trends (HR over a trip), drawn as dots on a baseline. */
export function Sparkline({ points, height = 64, color }: { points: number[]; height?: number; color?: string }) {
  const { colors } = useTheme();
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = Math.max(1, max - min);
  // At most ~80 columns so long trips do not create thousands of views.
  const step = Math.ceil(points.length / 80);
  const cols = points.filter((_, i) => i % step === 0);
  return (
    <View style={{ height, flexDirection: 'row', alignItems: 'flex-end', gap: 1 }}>
      {cols.map((p, i) => (
        <View key={i} style={{ flex: 1, height: 4 + ((p - min) / span) * (height - 4), backgroundColor: color ?? colors.textSecondary, opacity: 0.8, borderRadius: 1 }} />
      ))}
    </View>
  );
}
