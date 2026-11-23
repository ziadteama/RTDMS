import { Stack } from 'expo-router';

import { useT } from '@/i18n';
import { type, useTheme } from '@/theme';

export default function OnboardingLayout() {
  const t = useT();
  const { colors } = useTheme();
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.background },
        headerTintColor: colors.text,
        headerTitleStyle: { ...type.headline },
        headerShadowVisible: false,
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      <Stack.Screen name="consent" options={{ title: t('onb.consent.title') }} />
      <Stack.Screen name="permissions" options={{ title: t('onb.perm.title') }} />
      <Stack.Screen name="connect" options={{ title: t('onb.pair.title') }} />
      <Stack.Screen name="eye-calibration" options={{ title: t('cal.title') }} />
      <Stack.Screen name="emergency-contacts" options={{ title: t('onb.contacts.title') }} />
    </Stack>
  );
}
