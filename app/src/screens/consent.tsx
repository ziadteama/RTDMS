import { View } from 'react-native';

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
    <View style={{ gap: spacing.xl }}>
      <Text variant="body" tone="secondary">
        {t('onb.consent.lead')}
      </Text>
      {GROUPS.map((g) => (
        <View key={g.title} style={{ gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, borderCurve: 'continuous', padding: spacing.lg }}>
          <View style={{ flexDirection: 'row', gap: spacing.md, alignItems: 'center' }}>
            <Icon name={g.icon} size={22} color={colors.textSecondary} />
            <Text variant="headline" accessibilityRole="header" style={{ flex: 1 }}>
              {t(g.title)}
            </Text>
          </View>
          {g.items.map((i) => (
            <View key={i} style={{ flexDirection: 'row', gap: spacing.sm }}>
              <Text tone="tertiary">•</Text>
              <Text style={{ flex: 1 }}>{t(i)}</Text>
            </View>
          ))}
        </View>
      ))}
      <Text variant="caption" tone="secondary">
        {t('onb.consent.control')}
      </Text>
    </View>
  );
}
