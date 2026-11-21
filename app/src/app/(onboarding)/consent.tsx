import { router } from 'expo-router';
import { View } from 'react-native';

import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { useT } from '@/i18n';
import { ConsentStatement } from '@/screens/consent';
import { useSettings } from '@/state/settings';
import { spacing } from '@/theme';

export default function Consent() {
  const t = useT();
  return (
    <Screen>
      <ConsentStatement />
      <View style={{ gap: spacing.md }}>
        <Button
          title={t('onb.consent.agree')}
          size="lg"
          onPress={() => {
            useSettings.getState().set({ consentedAt: Date.now() });
            router.push('/permissions');
          }}
        />
      </View>
    </Screen>
  );
}
