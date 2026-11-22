import { View } from 'react-native';

import { Button } from '@/components/button';
import { Row, Section } from '@/components/list';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { spacing } from '@/theme';

export function IntroStep({
  isOnboarding,
  onStart,
  onLater,
}: {
  isOnboarding?: boolean;
  onStart: () => void;
  onLater?: () => void;
}) {
  const t = useT();

  return (
    <View style={{ flex: 1, justifyContent: 'space-between', gap: spacing.xl }}>
      <View style={{ gap: spacing.lg }}>
        <View style={{ gap: spacing.sm }}>
          <Text variant="title">{t('cal.eye.title')}</Text>
          <Text variant="body" tone="secondary">
            {t('cal.eye.subtitle')}
          </Text>
        </View>

        <Section>
          <Row icon="info" label={t('cal.eye.duration')} />
          <Row icon="phone" label={t('cal.eye.mount')} />
        </Section>
      </View>

      <View style={{ gap: spacing.sm }}>
        <Button title={t('cal.eye.start')} size="lg" onPress={onStart} />
        {isOnboarding && onLater ? (
          <Button
            title={t('cal.eye.later')}
            variant="ghost"
            size="md"
            onPress={onLater}
          />
        ) : null}
      </View>
    </View>
  );
}
