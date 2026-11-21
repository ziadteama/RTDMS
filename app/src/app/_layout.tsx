import { DarkTheme, DefaultTheme, Stack, ThemeProvider as NavigationTheme } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { dx } from '@/i18n/diagnostics';
import { useRuntime } from '@/services/runtime';
import { useSettings } from '@/state/settings';
import { ThemeProvider, useTheme } from '@/theme';

function Navigator() {
  const t = useT();
  const { scheme, colors } = useTheme();
  const onboarded = useSettings((s) => s.onboarded);
  useRuntime();
  const base = scheme === 'dark' ? DarkTheme : DefaultTheme;
  return (
    <NavigationTheme
      value={{
        ...base,
        colors: { ...base.colors, background: colors.background, card: colors.background, text: colors.text, border: colors.separator, primary: colors.text },
      }}
    >
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.background },
          headerTintColor: colors.text,
          headerShadowVisible: false,
          contentStyle: { backgroundColor: colors.background },
        }}
      >
        <Stack.Protected guard={!onboarded}>
          <Stack.Screen name="(onboarding)" options={{ headerShown: false }} />
        </Stack.Protected>
        <Stack.Protected guard={onboarded}>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="trip/[id]" options={{ title: t('trip.title') }} />
          <Stack.Screen name="incident/[id]" options={{ title: t('incident.title') }} />
          <Stack.Screen name="calibrate" options={{ title: t('cal.title'), presentation: 'modal' }} />
          <Stack.Screen name="contacts" options={{ title: t('contacts.title') }} />
          <Stack.Screen name="pair" options={{ title: t('onb.pair.title'), presentation: 'modal' }} />
          <Stack.Screen name="privacy" options={{ title: t('settings.whatStored') }} />
          <Stack.Screen
            name="diagnostics"
            options={{
              title: dx('diag.title'),
              headerTitle: () => (
                <View>
                  <Text variant="headline">{dx('diag.title')}</Text>
                  <Text variant="caption" tone="secondary">
                    {dx('diag.subtitle')}
                  </Text>
                </View>
              ),
            }}
          />
          <Stack.Screen
            name="sos"
            options={{ presentation: 'fullScreenModal', animation: 'fade', gestureEnabled: false, headerShown: false }}
          />
        </Stack.Protected>
      </Stack>
    </NavigationTheme>
  );
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <ThemeProvider>
        <Navigator />
      </ThemeProvider>
    </GestureHandlerRootView>
  );
}
