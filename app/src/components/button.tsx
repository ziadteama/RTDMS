import { useState, type ReactNode } from 'react';
import { ActivityIndicator, Pressable, View, type StyleProp, type ViewStyle } from 'react-native';
import Animated, { cubicBezier, useReducedMotion } from 'react-native-reanimated';

import { radius, spacing, touch, useTheme } from '@/theme';

import { Icon, type IconName } from './icon';
import { Text } from './text';

type Variant = 'primary' | 'secondary' | 'destructive' | 'ghost';

/**
 * Press feedback: 3% scale over 120 ms (expo-animation "press feedback" recipe). Feedback on
 * press-in, action on press-out. Min height 48 dp; 64 dp for in-car buttons; 96 dp for "I'm OK".
 */
export function Button({
  title,
  onPress,
  variant = 'primary',
  size = 'md',
  icon,
  loading,
  disabled,
  style,
  accessibilityHint,
  right,
  color,
}: {
  title: string;
  onPress?: () => void;
  variant?: Variant;
  size?: 'md' | 'lg' | 'xl';
  icon?: IconName;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  accessibilityHint?: string;
  right?: ReactNode;
  color?: string;
}) {
  const { colors } = useTheme();
  const [pressed, setPressed] = useState(false);
  // Reduce motion: no scale, a dim instead (state still visible, nothing moves).
  const reduced = useReducedMotion();
  const bg =
    variant === 'primary'
      ? colors.action
      : variant === 'destructive'
        ? colors.alert.continuous
        : variant === 'secondary'
          ? colors.surfaceRaised
          : 'transparent';
  const fg =
    color ??
    (variant === 'primary' ? colors.onAction : variant === 'destructive' ? colors.onAlert.continuous : colors.text);
  const off = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      onPressIn={() => setPressed(true)}
      onPressOut={() => setPressed(false)}
      disabled={off}
      hitSlop={8}
      pressRetentionOffset={16}
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      style={style}
    >
      <Animated.View
        style={{
          minHeight: size === 'xl' ? touch.huge : size === 'lg' ? touch.large : touch.min,
          paddingHorizontal: variant === 'ghost' ? spacing.md : spacing.xl,
          borderRadius: radius.md,
          borderCurve: 'continuous',
          backgroundColor: bg,
          opacity: off ? 0.45 : reduced && pressed ? 0.7 : 1,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
          gap: spacing.sm,
          transform: [{ scale: pressed && !reduced ? 0.97 : 1 }],
          transitionProperty: ['transform', 'opacity'],
          transitionDuration: 120,
          transitionTimingFunction: cubicBezier(0.23, 1, 0.32, 1),
        }}
      >
        {loading ? (
          <ActivityIndicator color={fg} />
        ) : (
          <>
            {icon ? <Icon name={icon} size={size === 'md' ? 22 : 26} color={fg} /> : null}
            <Text variant={size === 'xl' ? 'title' : size === 'lg' ? 'headline' : 'label'} color={fg}>
              {title}
            </Text>
            {right ? <View>{right}</View> : null}
          </>
        )}
      </Animated.View>
    </Pressable>
  );
}
