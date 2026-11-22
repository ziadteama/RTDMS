import { View } from 'react-native';

import { Button } from '@/components/button';
import { Icon } from '@/components/icon';
import { Row, Section } from '@/components/list';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { radius, spacing, useTheme } from '@/theme';

import type { FramingStatus } from './adapters';

export function FramingStep({
  isNative,
  status,
  isStable,
  onCancel,
}: {
  isNative: boolean;
  status: FramingStatus;
  isStable: boolean;
  onCancel: () => void;
}) {
  const t = useT();
  const { colors } = useTheme();

  return (
    <View style={{ flex: 1, justifyContent: 'space-between', gap: spacing.lg }}>
      <View style={{ gap: spacing.md }}>
        <Text variant="headline" align="center">
          {t('cal.eye.framing.title')}
        </Text>

        <View
          style={{
            height: 280,
            borderRadius: radius.lg,
            borderCurve: 'continuous',
            backgroundColor: isNative ? 'transparent' : colors.surface,
            overflow: 'hidden',
            justifyContent: 'center',
            alignItems: 'center',
          }}
        >
          {isNative ? null : (
            <View style={{ alignItems: 'center', gap: spacing.sm }}>
              <Icon name="camera" size={36} color={colors.textTertiary} />
            </View>
          )}

          <View
            style={{
              position: 'absolute',
              width: 180,
              height: 240,
              borderRadius: 90,
              borderWidth: 3,
              borderStyle: isStable ? 'solid' : 'dashed',
              borderColor: isStable ? colors.alert.none : colors.textSecondary,
              backgroundColor: 'transparent',
            }}
          />
        </View>

        <Section>
          <Row
            icon={status.faceInOval ? 'check' : 'close'}
            iconColor={status.faceInOval ? colors.alert.none : colors.textTertiary}
            label={t('cal.eye.framing.face')}
          />
          <Row
            icon={status.lightOk ? 'check' : 'close'}
            iconColor={status.lightOk ? colors.alert.none : colors.textTertiary}
            label={t('cal.eye.framing.light')}
          />
          <Row
            icon={status.headStraight ? 'check' : 'close'}
            iconColor={status.headStraight ? colors.alert.none : colors.textTertiary}
            label={t('cal.eye.framing.head')}
          />
        </Section>

        {isStable ? (
          <Text variant="caption" tone="secondary" align="center">
            {t('cal.eye.framing.hold')}
          </Text>
        ) : null}
      </View>

      <Button title={t('cal.eye.cancel')} variant="ghost" size="md" onPress={onCancel} />
    </View>
  );
}
