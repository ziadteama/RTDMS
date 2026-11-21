import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { ContactsEditor } from '@/screens/contacts';
import { useSettings } from '@/state/settings';

export default function EmergencyContacts() {
  const t = useT();
  return (
    <Screen>
      <Text tone="secondary">{t('onb.contacts.lead')}</Text>
      <ContactsEditor />
      {/* Finishing flips the Stack.Protected guard: the tabs replace onboarding. */}
      <Button title={t('onb.finish')} size="lg" onPress={() => useSettings.getState().set({ onboarded: true })} />
    </Screen>
  );
}
