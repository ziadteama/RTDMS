import { Fragment } from 'react';
import { StyleSheet, View } from 'react-native';

import { Icon, type IconName } from '@/components/icon';
import { Text } from '@/components/text';
import { useT, type StringKey } from '@/i18n';
import { radius, spacing, useTheme } from '@/theme';

const GROUPS: { title: StringKey; icon: IconName; items: StringKey[] }[] = [
  { title: 'onb.consent.processed', icon: 'eye', items: ['onb.consent.p1', 'onb.consent.p2'] },
  { title: 'onb.consent.stored', icon: 'phone', items: ['onb.consent.s1', 'onb.consent.s2', 'onb.consent.s3'] },
  { title: 'onb.consent.incident', icon: 'crash', items: ['onb.consent.i1', 'onb.consent.i2'] },
  { title: 'onb.consent.never', icon: 'close', items: ['onb.consent.n1'] },
];

/** The plain "what is processed and stored" statement (consent screen and Settings → Privacy). */
export function ConsentStatement() {
  const t = useT();
  const { colors } = useTheme();
  return (
    <View style={{ gap: spacing.md }}>
      <View
        style={{
          backgroundColor: colors.surface,
          borderRadius: radius.md,
          borderCurve: 'continuous',
          overflow: 'hidden',
        }}
      >
        {GROUPS.map((g, gi) => (
          <Fragment key={g.title}>
            {gi > 0 ? (
              <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.separator, marginStart: spacing.lg }} />
            ) : null}
            <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, gap: spacing.xs }}>
              <View style={{ flexDirection: 'row', gap: spacing.md, alignItems: 'center' }}>
                <Icon name={g.icon} size={20} color={colors.textSecondary} />
                <Text variant="label" accessibilityRole="header" style={{ flex: 1 }}>
                  {t(g.title)}
                </Text>
              </View>
              <View style={{ gap: spacing.xxs, paddingStart: spacing.xl + spacing.xs }}>
                {g.items.map((i) => (
                  <Text key={i} variant="caption" tone="secondary">
                    {t(i)}
                  </Text>
                ))}
              </View>
            </View>
          </Fragment>
        ))}
      </View>
      <Text variant="caption" tone="tertiary">
        {t('onb.consent.control')}
      </Text>
    </View>
  );
}
