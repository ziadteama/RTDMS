import { View } from 'react-native';

import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { ContactsEditor } from '@/screens/contacts';
import { useSettings } from '@/state/settings';
import { spacing } from '@/theme';

export default function EmergencyContacts() {
  const t = useT();
  return (
    <Screen contentContainerStyle={{ flexGrow: 1, justifyContent: 'space-between' }}>
      <View style={{ gap: spacing.lg }}>
        <Text tone="secondary">{t('onb.contacts.lead')}</Text>
        <ContactsEditor />
      </View>
      {/* Finishing flips the Stack.Protected guard: the tabs replace onboarding. */}
      <Button title={t('onb.finish')} size="lg" onPress={() => useSettings.getState().set({ onboarded: true })} />
    </Screen>
  );
}
