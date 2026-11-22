import { View } from 'react-native';

import { Button } from '@/components/button';
import { Row, Section } from '@/components/list';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { spacing, useTheme } from '@/theme';

import type { CalibrationQuality } from './adapters';

export function ResultStep({
  quality,
  isSaved,
  isSynced,
  onSave,
  onRetry,
  onDone,
  onCancel,
}: {
  quality: CalibrationQuality;
  isSaved: boolean;
  isSynced: boolean;
  onSave: () => void;
  onRetry: () => void;
  onDone: () => void;
  onCancel?: () => void;
}) {
  const t = useT();
  const { colors } = useTheme();

  const isPoor = quality === 'poor';
  const qualityColor =
    quality === 'good'
      ? colors.alert.none
      : quality === 'fair'
        ? colors.alert.short_beep
        : colors.alert.continuous;

  const headline = t(`cal.eye.result.${quality}`);
  const description = t(`cal.eye.result.${quality}Desc`);

  return (
    <View style={{ flex: 1, justifyContent: 'space-between', gap: spacing.xl }}>
      <View style={{ gap: spacing.lg }}>
        <View style={{ gap: spacing.sm }}>
          <Text variant="title" color={qualityColor}>
            {headline}
          </Text>
          <Text variant="body" tone="secondary">
            {description}
          </Text>
        </View>

        {isSaved ? (
          <Section>
            <Row
              icon={isSynced ? 'check' : 'info'}
              iconColor={isSynced ? colors.alert.none : colors.textSecondary}
              label={t(isSynced ? 'cal.eye.sync.saved' : 'cal.eye.sync.pending')}
            />
          </Section>
        ) : null}
      </View>

      <View style={{ gap: spacing.sm }}>
        {isSaved ? (
          <Button title={t('cal.eye.done')} size="lg" onPress={onDone} />
        ) : isPoor ? (
          <>
            <Button title={t('cal.eye.retry')} size="lg" onPress={onRetry} />
            <Button
              title={t('cal.eye.cancel')}
              variant="ghost"
              size="md"
              onPress={onCancel ?? onDone}
            />
          </>
        ) : (
          <>
            <Button title={t('cal.eye.save')} size="lg" onPress={onSave} />
            <Button
              title={t('cal.eye.retry')}
              variant="secondary"
              size="md"
              onPress={onRetry}
            />
          </>
        )}
      </View>
    </View>
  );
}
