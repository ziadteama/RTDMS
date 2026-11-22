import { View } from 'react-native';

import { ProgressBar } from '@/components/progress-bar';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { radius, spacing, useTheme } from '@/theme';

export function CountdownRing({
  seconds,
  totalSeconds,
  running = true,
}: {
  seconds: number;
  totalSeconds: number;
  running?: boolean;
}) {
  const t = useT();
  const { colors } = useTheme();

  return (
    <View style={{ alignItems: 'center', gap: spacing.xl }}>
      <View
        style={{
          width: 200,
          height: 200,
          borderRadius: radius.full,
          borderWidth: spacing.sm,
          borderColor: colors.surfaceRaised,
          backgroundColor: colors.surface,
          alignItems: 'center',
          justifyContent: 'center',
        }}
        accessibilityRole="timer"
        accessibilityLiveRegion="assertive"
      >
        <Text variant="countdown" align="center">
          {Math.max(0, seconds)}
        </Text>
        <Text variant="caption" tone="secondary" align="center">
          {t('live.s')}
        </Text>
      </View>
      <View style={{ width: '100%', maxWidth: 280 }}>
        <ProgressBar
          key={`${totalSeconds}-${running ? 'run' : 'stop'}`}
          durationMs={totalSeconds * 1000}
          running={running}
          color={colors.action}
        />
      </View>
    </View>
  );
}
