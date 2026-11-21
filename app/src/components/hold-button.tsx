import { useEffect } from 'react';
import { Pressable, View } from 'react-native';
import Animated, {
  Easing,
  cancelAnimation,
  useAnimatedReaction,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import * as Haptics from 'expo-haptics';

import { radius, spacing, touch, useTheme } from '@/theme';

import { Icon } from './icon';
import { Text } from './text';

/**
 * Hold-to-confirm (gestures skill): the fill grows LINEARLY while held — it shows time passing —
 * and snaps back fast with ease-out on early release. Fires once when the fill completes, from a
 * UI-thread reaction, so a mis-tap in a moving car cannot start an SOS.
 */
export function HoldButton({ label, hint, holdMs = 2000, onComplete }: { label: string; hint: string; holdMs?: number; onComplete: () => void }) {
  const { colors } = useTheme();
  const progress = useSharedValue(0);

  useAnimatedReaction(
    () => progress.get() >= 1,
    (done, was) => {
      if (done && !was) {
        scheduleOnRN(onComplete);
        progress.set(0);
      }
    },
  );
  useEffect(() => () => cancelAnimation(progress), [progress]);

  const fill = useAnimatedStyle(() => ({ transform: [{ scaleX: progress.get() }] }));

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      onPressIn={() => {
        if (process.env.EXPO_OS !== 'web') void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
        progress.set(withTiming(1, { duration: holdMs * (1 - progress.get()), easing: Easing.linear }));
      }}
      onPressOut={() => {
        if (progress.get() < 1) progress.set(withTiming(0, { duration: 150, easing: Easing.bezier(0.23, 1, 0.32, 1) }));
      }}
      // a long press must not also count as a tap anywhere else
      delayLongPress={holdMs * 2}
    >
      <View
        style={{
          minHeight: touch.large,
          borderRadius: radius.md,
          borderCurve: 'continuous',
          backgroundColor: colors.surfaceRaised,
          overflow: 'hidden',
          justifyContent: 'center',
        }}
      >
        <Animated.View
          style={[
            {
              position: 'absolute',
              top: 0,
              bottom: 0,
              start: 0,
              end: 0,
              backgroundColor: colors.alert.max,
              transformOrigin: 'left',
            },
            fill,
          ]}
        />
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, paddingHorizontal: spacing.xl }}>
          <Icon name="sos" color={colors.text} />
          <View>
            <Text variant="headline">{label}</Text>
            <Text variant="caption" tone="secondary">
              {hint}
            </Text>
          </View>
        </View>
      </View>
    </Pressable>
  );
}
