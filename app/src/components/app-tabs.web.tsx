import { TabList, TabSlot, TabTrigger, Tabs, type TabTriggerSlotProps } from 'expo-router/ui';
import { Pressable, View } from 'react-native';

import { useT } from '@/i18n';
import { spacing, touch, useTheme } from '@/theme';

import { Icon, type IconName } from './icon';
import { Text } from './text';

// Web build only (screenshots / UI checks): a bottom bar shaped like the Material 3 navigation bar
// that NativeTabs renders on Android.
function TabButton({ isFocused, icon, label, onPress }: TabTriggerSlotProps & { icon: IconName; label: string }) {
  const { colors } = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="tab" accessibilityState={{ selected: !!isFocused }} style={{ flex: 1, alignItems: 'center', gap: spacing.xs, paddingVertical: spacing.sm, minHeight: touch.large }}>
      <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.xs, borderRadius: 16, backgroundColor: isFocused ? colors.surfaceRaised : 'transparent' }}>
        <Icon name={icon} color={isFocused ? colors.text : colors.textTertiary} />
      </View>
      <Text variant="caption" color={isFocused ? colors.text : colors.textTertiary}>
        {label}
      </Text>
    </Pressable>
  );
}

export function AppTabs() {
  const t = useT();
  const { colors } = useTheme();
  return (
    <Tabs>
      <TabSlot style={{ flex: 1 }} />
      <TabList style={{ backgroundColor: colors.surface, flexDirection: 'row' }}>
        <TabTrigger name="live" href="/live" asChild>
          <TabButton icon="live" label={t('tab.live')} />
        </TabTrigger>
        <TabTrigger name="trips" href="/trips" asChild>
          <TabButton icon="trips" label={t('tab.trips')} />
        </TabTrigger>
        <TabTrigger name="health" href="/health" asChild>
          <TabButton icon="health" label={t('tab.health')} />
        </TabTrigger>
        <TabTrigger name="settings" href="/settings" asChild>
          <TabButton icon="settings" label={t('tab.settings')} />
        </TabTrigger>
      </TabList>
    </Tabs>
  );
}
