import { router } from 'expo-router';
import { View } from 'react-native';

import { Button } from '@/components/button';
import { LiveView } from '@/components/live-view';
import { ProgressBar } from '@/components/progress-bar';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { pi } from '@/services/pi';
import { spacing, useTheme } from '@/theme';

import { CLOSED_MS, OPEN_MS, type Phase } from './machine';
import { usePiCalibration } from './use-pi-calibration';

function CalibrationContent({ phase, online }: { phase: Phase; online: boolean }) {
  const t = useT();
  const { colors } = useTheme();
  const step = phase === 'open' ? t('cal.step1') : phase === 'closed' ? t('cal.step2') : phase === 'waiting' ? t('cal.waiting') : null;
  return (
    <View style={{ gap: spacing.lg }}>
      <LiveView url={online ? pi().streamUrl() : null} emptyLabel={t('live.noVideo')} />
      {phase === 'intro' ? <Text tone="secondary">{online ? t('cal.intro') : t('cal.offline')}</Text> : null}
      {step ? (
        <View style={{ gap: spacing.md }} accessibilityLiveRegion="assertive">
          <Text variant="title">{step}</Text>
          {phase === 'open' || phase === 'closed' ? (
            <ProgressBar key={phase} durationMs={phase === 'open' ? OPEN_MS : CLOSED_MS} running />
          ) : null}
        </View>
      ) : null}
      {phase === 'done' ? (
        <Text variant="title" color={colors.alert.none}>
          {t('cal.done')}
        </Text>
      ) : null}
      {phase === 'failed' ? (
        <Text variant="headline" color={colors.alert.continuous} selectable>
          {t('cal.failed')}
        </Text>
      ) : null}
    </View>
  );
}

export function PiCalibrationScreen({ onDone = () => router.back(), isOnboarding = false }: { onDone?: () => void; isOnboarding?: boolean }) {
  const t = useT();
  const { phase, online, start } = usePiCalibration();
  return (
    <Screen contentContainerStyle={{ flexGrow: 1, justifyContent: 'space-between' }}>
      <CalibrationContent phase={phase} online={online} />
      {phase === 'intro' || phase === 'failed' ? (
        <Button title={phase === 'failed' ? t('cal.again') : t('cal.start')} size="lg" disabled={!online} onPress={() => void start()} />
      ) : null}
      {phase === 'done' ? <Button title={t('cal.close')} size="lg" onPress={onDone} /> : null}
      {isOnboarding && (!online || phase === 'failed') ? (
        <Button title={t('cal.skip')} variant="ghost" onPress={onDone} />
      ) : null}
    </Screen>
  );
}
