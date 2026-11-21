import { Stack } from 'expo-router';

import { useT } from '@/i18n';
import { useTheme } from '@/theme';

export default function Layout() {
  const t = useT();
  const { colors } = useTheme();
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.background },
        headerTintColor: colors.text,
        headerShadowVisible: false,
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      <Stack.Screen name="index" options={{ title: t('tab.live') }} />
    </Stack>
  );
}
