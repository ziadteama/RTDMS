import { View } from 'react-native';

import { spacing, useTheme } from '@/theme';

import { Text } from './text';

/** Label over a big tabular value. `null` renders a dash: no data is never shown as 0. */
export function Metric({
  label,
  value,
  unit,
  note,
  color,
}: {
  label: string;
  value: string | number | null;
  unit?: string;
  note?: string;
  color?: string;
}) {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, minWidth: 140, gap: spacing.xxs }} accessible accessibilityLabel={`${label} ${value ?? '—'} ${unit ?? ''} ${note ?? ''}`}>
      <Text variant="caption" tone="secondary" numberOfLines={1}>
        {label}
      </Text>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: spacing.xs }}>
        <Text variant="metric" color={value === null ? colors.textTertiary : color} selectable>
          {value ?? '—'}
        </Text>
        {unit && value !== null ? (
          <Text variant="label" tone="secondary">
            {unit}
          </Text>
        ) : null}
      </View>
      {note ? (
        <Text variant="caption" tone="tertiary" numberOfLines={1}>
          {note}
        </Text>
      ) : null}
    </View>
  );
}
