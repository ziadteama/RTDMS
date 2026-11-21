import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { View } from 'react-native';

import { Button } from '@/components/button';
import { LiveView } from '@/components/live-view';
import { ProgressBar } from '@/components/progress-bar';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { speak } from '@/services/alerts';
import { pi } from '@/services/pi';
import { useLive } from '@/state/live';
import { spacing, useTheme } from '@/theme';

/** stream.py calibration: 10 s eyes open looking ahead, then 3 s eyes closed (drowsiness.py). */
const OPEN_MS = 10_000;
const CLOSED_MS = 3_000;
const RESULT_TIMEOUT_MS = 15_000;

type Phase = 'intro' | 'open' | 'closed' | 'waiting' | 'done' | 'failed';

export default function Calibrate() {
  const t = useT();
  const { colors } = useTheme();
  const online = useLive((s) => s.connection === 'online');
  const message = useLive((s) => s.status?.drowsiness?.message ?? '');
  const [phase, setPhase] = useState<Phase>('intro');
  const [failure, setFailure] = useState('');

  // The Pi reports the result in /status drowsiness.message: derive it, do not copy it into state.
  const listening = phase === 'waiting' || phase === 'closed';
  const result: Phase | null = !listening ? null : message === 'calibrated' ? 'done' : message.startsWith('calibration failed') ? 'failed' : null;
  const shown: Phase = result ?? phase;
  const reason = result === 'failed' ? message.replace('calibration failed: ', '') : failure;
  useEffect(() => {
    if (result === 'done') speak('cal.done');
  }, [result]);

  useEffect(() => {
    if (phase === 'open') {
      const id = setTimeout(() => {
        setPhase('closed');
        speak('cal.step2'); // the driver cannot read the screen with eyes closed
      }, OPEN_MS);
      return () => clearTimeout(id);
    }
    if (phase === 'closed') {
      const id = setTimeout(() => setPhase('waiting'), CLOSED_MS);
      return () => clearTimeout(id);
    }
    if (phase === 'waiting' && result === null) {
      const id = setTimeout(() => {
        setFailure('timeout');
        setPhase('failed');
      }, RESULT_TIMEOUT_MS);
      return () => clearTimeout(id);
    }
  }, [phase, result]);

  const start = async () => {
    try {
      await pi().send('POST', '/calibrate');
      setPhase('open');
      speak('cal.step1');
    } catch {
      setFailure('POST /calibrate');
      setPhase('failed');
    }
  };

  const step = shown === 'open' ? t('cal.step1') : shown === 'closed' ? t('cal.step2') : shown === 'waiting' ? t('cal.waiting') : null;
  return (
    <Screen contentContainerStyle={{ flexGrow: 1, justifyContent: 'space-between' }}>
      <View style={{ gap: spacing.lg }}>
        <LiveView url={online ? pi().streamUrl() : null} emptyLabel={t('live.noVideo')} />
        {shown === 'intro' ? <Text tone="secondary">{online ? t('cal.intro') : t('cal.offline')}</Text> : null}
        {step ? (
          <View style={{ gap: spacing.md }} accessibilityLiveRegion="assertive">
            <Text variant="title">{step}</Text>
            {shown === 'open' || shown === 'closed' ? (
              <ProgressBar key={shown} durationMs={shown === 'open' ? OPEN_MS : CLOSED_MS} running />
            ) : null}
          </View>
        ) : null}
        {shown === 'done' ? (
          <Text variant="title" color={colors.alert.none}>
            {t('cal.done')}
          </Text>
        ) : null}
        {shown === 'failed' ? (
          <Text variant="headline" color={colors.alert.continuous} selectable>
            {t('cal.failed', { m: reason })}
          </Text>
        ) : null}
      </View>
      {shown === 'intro' || shown === 'failed' ? (
        <Button title={shown === 'failed' ? t('cal.again') : t('cal.start')} size="lg" disabled={!online} onPress={() => void start()} />
      ) : null}
      {shown === 'done' ? <Button title={t('cal.close')} size="lg" onPress={() => router.back()} /> : null}
    </Screen>
  );
}
