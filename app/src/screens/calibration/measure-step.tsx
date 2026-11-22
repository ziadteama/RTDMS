import { View } from 'react-native';

import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { spacing } from '@/theme';

import { CountdownRing } from './countdown-ring';

export function MeasureStep({
  phase,
  secondsRemaining,
}: {
  phase: 'open' | 'closed';
  secondsRemaining: number;
}) {
  const t = useT();
  const isOpen = phase === 'open';

  return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', gap: spacing.xxl }}>
      <View style={{ gap: spacing.sm, alignItems: 'center' }}>
        <Text variant="title" align="center">
          {isOpen ? t('cal.eye.open.title') : t('cal.eye.closed.title')}
        </Text>
        <Text variant="body" tone="secondary" align="center">
          {isOpen ? t('cal.eye.open.subtitle') : t('cal.eye.closed.subtitle')}
        </Text>
      </View>

      <CountdownRing
        seconds={secondsRemaining}
        totalSeconds={isOpen ? 10 : 3}
        running
      />
    </View>
  );
}
