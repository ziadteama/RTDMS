import { router } from 'expo-router';
import { View } from 'react-native';

import { Button } from '@/components/button';
import { Choice } from '@/components/controls';
import { Row, Section } from '@/components/list';
import { Screen } from '@/components/screen';
import { useT } from '@/i18n';
import { ConsentStatement } from '@/screens/consent';
import { useSettings, type Language } from '@/state/settings';
import { spacing } from '@/theme';

export default function Consent() {
  const t = useT();
  const language = useSettings((s) => s.language);
  return (
    <Screen>
      <Section>
        <Row
          label={t('settings.language')}
          right={
            <Choice<Language>
              label={t('settings.language')}
              value={language}
              options={[
                { value: 'en', label: 'English' },
                { value: 'ar', label: 'العربية' },
              ]}
              onChange={(v) => useSettings.getState().set({ language: v })}
            />
          }
        />
      </Section>
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
