import { memo } from 'react';
import { View } from 'react-native';
import Animated, { cubicBezier, useReducedMotion } from 'react-native-reanimated';

import { useT } from '@/i18n';
import type { DriverState } from '@/pi/alert';
import { ALERT_PRESENTATION } from '@/pi/alert';
import type { AlertPattern } from '@/pi/types';
import { motion, radius, spacing, useTheme } from '@/theme';

import { Text } from './text';

const PULSE = { from: { opacity: 1 }, to: { opacity: 0.72 } };

/**
 * The one thing a driver reads at a glance. Label = the Pi's driver state; color = fusion's
 * AlertPattern (never derived on the phone). Color cross-fades on change (kept under reduce
 * motion: it explains the change); only "max" pulses, and not under reduce motion.
 */
export const StateIndicator = memo(function StateIndicator({
  state,
  pattern,
  size = 'compact',
  detail,
}: {
  state: DriverState | 'paused';
  pattern: AlertPattern | null;
  size?: 'compact' | 'full';
  detail?: string;
}) {
  const t = useT();
  const { colors } = useTheme();
  const reduced = useReducedMotion();
  const known = pattern !== null && state !== 'offline' && state !== 'paused';
  const bg = known ? colors.alert[pattern] : colors.surfaceRaised;
  const fg = known ? colors.onAlert[pattern] : colors.textSecondary;
  const pulse = known && ALERT_PRESENTATION[pattern].pulse && !reduced;
  const full = size === 'full';
  return (
    <Animated.View
      accessibilityRole="summary"
      accessibilityLiveRegion="assertive"
      accessibilityLabel={`${t(`state.${state}`)}. ${known ? t(`pattern.${pattern}`) : t('pattern.unknown')}`}
      style={[
        {
          backgroundColor: bg,
          borderRadius: radius.lg,
          borderCurve: 'continuous',
          paddingVertical: full ? spacing.xxxl : spacing.xl,
          paddingHorizontal: spacing.xl,
          gap: spacing.sm,
          flex: full ? 1 : undefined,
          justifyContent: 'center',
          transitionProperty: 'backgroundColor',
          transitionDuration: motion.base,
          transitionTimingFunction: cubicBezier(0.23, 1, 0.32, 1),
        },
        pulse && {
          animationName: PULSE,
          animationDuration: motion.pulse,
          animationIterationCount: 'infinite',
          animationDirection: 'alternate',
          animationTimingFunction: cubicBezier(0.77, 0, 0.175, 1),
        },
      ]}
    >
      <Text variant="state" color={fg} align={full ? 'center' : 'auto'} numberOfLines={2} adjustsFontSizeToFit>
        {t(`state.${state}`)}
      </Text>
      <View style={{ alignItems: full ? 'center' : 'flex-start' }}>
        <Text variant="headline" color={fg} style={{ opacity: 0.9 }}>
          {known ? t(`pattern.${pattern}`) : t('pattern.unknown')}
        </Text>
        {detail ? (
          <Text variant="body" color={fg} style={{ opacity: 0.85 }} numberOfLines={2}>
            {detail}
          </Text>
        ) : null}
      </View>
    </Animated.View>
  );
});
