import { NativeTabs } from 'expo-router/native-tabs';

import { useT } from '@/i18n';
import { useTheme } from '@/theme';

/** The platform tab bar (Material 3 navigation bar on Android). Tabs switch without animation. */
export function AppTabs() {
  const t = useT();
  const { colors } = useTheme();
  return (
    <NativeTabs
      backgroundColor={colors.surface}
      indicatorColor={colors.surfaceRaised}
      iconColor={{ default: colors.textTertiary, selected: colors.text }}
      labelStyle={{ default: { color: colors.textTertiary }, selected: { color: colors.text } }}
    >
      <NativeTabs.Trigger name="live">
        <NativeTabs.Trigger.Label>{t('tab.live')}</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="video" md="videocam" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="trips">
        <NativeTabs.Trigger.Label>{t('tab.trips')}</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="road.lanes" md="route" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="health">
        <NativeTabs.Trigger.Label>{t('tab.health')}</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="cpu" md="memory" />
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="settings">
        <NativeTabs.Trigger.Label>{t('tab.settings')}</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="gearshape" md="settings" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
