import { View } from 'react-native';

import { Button } from '@/components/button';
import { Text } from '@/components/text';
import { useT, type StringKey } from '@/i18n';
import { spacing, useTheme } from '@/theme';

import type { BuildProfileFailureReason } from './adapters';

const REASON_KEYS: Record<BuildProfileFailureReason, { title: StringKey; desc: StringKey }> = {
  no_face: { title: 'cal.eye.fail.noFace', desc: 'cal.eye.fail.noFaceDesc' },
  too_dark: { title: 'cal.eye.fail.tooDark', desc: 'cal.eye.fail.tooDarkDesc' },
  head_turned: { title: 'cal.eye.fail.headTurned', desc: 'cal.eye.fail.headTurnedDesc' },
  eyes_not_shut: { title: 'cal.eye.fail.eyesNotShut', desc: 'cal.eye.fail.eyesNotShutDesc' },
  too_few_samples: { title: 'cal.eye.fail.tooFewSamples', desc: 'cal.eye.fail.tooFewSamplesDesc' },
};

export function FailureStep({
  reason,
  onRetry,
  onCancel,
}: {
  reason: BuildProfileFailureReason;
  onRetry: () => void;
  onCancel: () => void;
}) {
  const t = useT();
  const { colors } = useTheme();

  const keys = REASON_KEYS[reason] ?? REASON_KEYS.too_few_samples;

  return (
    <View style={{ flex: 1, justifyContent: 'space-between', gap: spacing.xl }}>
      <View style={{ gap: spacing.sm }}>
        <Text variant="title" color={colors.alert.continuous}>
          {t(keys.title)}
        </Text>
        <Text variant="body" tone="secondary">
          {t(keys.desc)}
        </Text>
      </View>

      <View style={{ gap: spacing.sm }}>
        <Button title={t('cal.eye.retry')} size="lg" onPress={onRetry} />
        <Button
          title={t('cal.eye.cancel')}
          variant="ghost"
          size="md"
          onPress={onCancel}
        />
      </View>
    </View>
  );
}
