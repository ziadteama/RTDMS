import { useState } from 'react';
import { Linking, Platform, View } from 'react-native';

import { Button } from '@/components/button';
import { Row, Section } from '@/components/list';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { permission } from '@/services/permissions';
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
  const [permissionDenied, setPermissionDenied] = useState(false);

  const handleStart = async () => {
    if (Platform.OS === 'web') {
      setPermissionDenied(false);
      onStart();
      return;
    }
    try {
      const status = await permission('camera', true);
      if (status === 'denied') {
        setPermissionDenied(true);
        return;
      }
    } catch {
      // Camera permission module unavailable on web/Jest -> fail open
    }
    setPermissionDenied(false);
    onStart();
  };

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
        {permissionDenied ? (
          <View style={{ gap: spacing.sm, alignItems: 'center' }}>
            <Text variant="body" tone="secondary" align="center">
              {t('cal.eye.perm.denied')}
            </Text>
            <Button
              title={t('cal.eye.perm.openSettings')}
              variant="secondary"
              size="md"
              onPress={() => void Linking.openSettings()}
            />
            <Button title={t('cal.eye.start')} size="lg" onPress={() => void handleStart()} />
          </View>
        ) : (
          <Button title={t('cal.eye.start')} size="lg" onPress={() => void handleStart()} />
        )}
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
