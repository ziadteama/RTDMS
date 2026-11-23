import { router } from 'expo-router';
import { View } from 'react-native';

import { Button } from '@/components/button';
import { LiveView } from '@/components/live-view';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { pi } from '@/services/pi';
import { spacing, useTheme } from '@/theme';

import { stepCopy, type State } from './machine';
import { usePiCalibration } from './use-pi-calibration';

function CalibrationContent({ phase, step, left, online }: State & { online: boolean }) {
  const t = useT();
  const { colors } = useTheme();
  const prompt = phase === 'starting' || phase === 'following'
    ? step ? t(stepCopy[step]) : t('cal.starting') : null;
  return (
    <View style={{ gap: spacing.lg }}>
      <LiveView url={online ? pi().streamUrl() : null} emptyLabel={t('live.noVideo')} />
      {phase === 'intro' ? <Text tone="secondary">{online ? t('cal.intro') : t('cal.offline')}</Text> : null}
      {prompt ? (
        <View style={{ gap: spacing.md }} accessibilityLiveRegion="assertive">
          <Text variant="title">{prompt}</Text>
          {phase === 'following' && left !== null ? <Text>{`${Math.ceil(left)} s`}</Text> : null}
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
  const calibration = usePiCalibration();
  const { phase, online, start } = calibration;
  return (
    <Screen contentContainerStyle={{ flexGrow: 1, justifyContent: 'space-between' }}>
      <CalibrationContent {...calibration} />
      {phase === 'intro' || phase === 'failed' ? (
        <Button title={phase === 'failed' ? t('cal.again') : t('cal.start')} size="lg" disabled={!online} onPress={() => void start()} />
      ) : null}
      {phase === 'done' ? <Button title={t('cal.close')} size="lg" onPress={onDone} /> : null}
      {isOnboarding && phase !== 'done' ? (
        <Button title={t('cal.skip')} variant="ghost" onPress={onDone} />
      ) : null}
    </Screen>
  );
}
