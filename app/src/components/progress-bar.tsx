import { useEffect } from 'react';
import { View } from 'react-native';
import Animated, { Easing, cancelAnimation, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { radius, useTheme } from '@/theme';

/**
 * Time-remaining bar. Linear on purpose: it shows time passing (any other curve lies about how
 * long is left). Runs on the UI thread; restarting `key`/`durationMs` restarts it.
 */
export function ProgressBar({ durationMs, running, color, height = 8 }: { durationMs: number; running: boolean; color?: string; height?: number }) {
  const { colors } = useTheme();
  const p = useSharedValue(0);
  useEffect(() => {
    if (running) {
      p.set(0);
      p.set(withTiming(1, { duration: durationMs, easing: Easing.linear }));
    } else cancelAnimation(p);
    return () => cancelAnimation(p);
  }, [running, durationMs, p]);
  const fill = useAnimatedStyle(() => ({ transform: [{ scaleX: p.get() }] }));
  return (
    <View style={{ height, borderRadius: radius.full, backgroundColor: colors.surfaceRaised, overflow: 'hidden' }}>
      <Animated.View style={[{ flex: 1, backgroundColor: color ?? colors.text, transformOrigin: 'left' }, fill]} />
    </View>
  );
}
