import { Children, Fragment, type ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { radius, spacing, touch, useTheme } from '@/theme';

import { Icon, type IconName } from './icon';
import { Text } from './text';

/**
 * Grouped list: one surface per group, hairline separators, no card per row and no borders.
 * Rows highlight their background on press (they never scale).
 */
export function Section({ title, footer, children }: { title?: string; footer?: string; children: ReactNode }) {
  const { colors } = useTheme();
  const rows = Children.toArray(children).filter(Boolean);
  return (
    <View style={{ gap: spacing.sm }}>
      {title ? (
        <Text variant="label" tone="secondary" style={{ paddingHorizontal: spacing.lg }} accessibilityRole="header">
          {title}
        </Text>
      ) : null}
      <View style={{ backgroundColor: colors.surface, borderRadius: radius.md, borderCurve: 'continuous', overflow: 'hidden' }}>
        {rows.map((row, i) => (
          <Fragment key={i}>
            {i > 0 ? (
              <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.separator, marginStart: spacing.lg }} />
            ) : null}
            {row}
          </Fragment>
        ))}
      </View>
      {footer ? (
        <Text variant="caption" tone="tertiary" style={{ paddingHorizontal: spacing.lg }}>
          {footer}
        </Text>
      ) : null}
    </View>
  );
}

export function Row({
  label,
  detail,
  value,
  icon,
  iconColor,
  onPress,
  chevron,
  destructive,
  disabled,
  right,
  valueColor,
}: {
  label: string;
  detail?: string;
  value?: string;
  icon?: IconName;
  iconColor?: string;
  onPress?: () => void;
  chevron?: boolean;
  destructive?: boolean;
  disabled?: boolean;
  right?: ReactNode;
  valueColor?: string;
}) {
  const { colors } = useTheme();
  const labelColor = destructive ? colors.alert.continuous : colors.text;
  const body = (pressed: boolean) => (
    <View
      style={{
        minHeight: touch.min + spacing.sm,
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.md,
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        backgroundColor: pressed ? colors.surfaceRaised : 'transparent',
        opacity: disabled ? 0.45 : 1,
      }}
    >
      {icon ? <Icon name={icon} size={22} color={iconColor ?? (destructive ? colors.alert.continuous : colors.textSecondary)} /> : null}
      <View style={{ flex: 1, gap: spacing.xxs }}>
        <Text variant="body" color={labelColor}>
          {label}
        </Text>
        {detail ? (
          <Text variant="caption" tone="secondary">
            {detail}
          </Text>
        ) : null}
      </View>
      {value !== undefined ? (
        <Text variant="body" tone="secondary" color={valueColor} selectable style={{ fontVariant: ['tabular-nums'] }}>
          {value}
        </Text>
      ) : null}
      {right}
      {chevron ? <Icon name="chevron" size={20} color={colors.textTertiary} /> : null}
    </View>
  );
  if (!onPress) return body(false);
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button" accessibilityLabel={label}>
      {({ pressed }) => body(pressed)}
    </Pressable>
  );
}
