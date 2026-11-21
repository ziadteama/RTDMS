import { View } from 'react-native';

import { radius, spacing, useTheme } from '@/theme';

import { Icon, type IconName } from './icon';
import { Text } from './text';

/** A state the driver must know about (offline, paused, demo, no GPS). Not dismissible. */
export function Banner({
  icon,
  title,
  detail,
  tone = 'neutral',
}: {
  icon: IconName;
  title: string;
  detail?: string;
  tone?: 'neutral' | 'warning' | 'danger';
}) {
  const { colors } = useTheme();
  const accent = tone === 'danger' ? colors.alert.continuous : tone === 'warning' ? colors.alert.short_beep : colors.textSecondary;
  return (
    <View
      accessibilityRole="alert"
      style={{
        flexDirection: 'row',
        gap: spacing.md,
        alignItems: 'center',
        padding: spacing.md,
        backgroundColor: colors.surfaceRaised,
        borderRadius: radius.md,
        borderCurve: 'continuous',
        overflow: 'hidden',
      }}
    >
      {/* Leading accent bar */}
      <View style={{ alignSelf: 'stretch', width: 4, marginVertical: -spacing.md, marginLeft: -spacing.md, backgroundColor: accent }} />
      <Icon name={icon} size={22} color={accent} />
      <View style={{ flex: 1, gap: spacing.xxs }}>
        <Text variant="label">{title}</Text>
        {detail ? (
          <Text variant="caption" tone="secondary">
            {detail}
          </Text>
        ) : null}
      </View>
    </View>
  );
}
