import { Screen } from '@/components/screen';
import { ContactsEditor } from '@/screens/contacts';

export default function Contacts() {
  return (
    <Screen contentContainerStyle={{ flexGrow: 1 }}>
      <ContactsEditor />
    </Screen>
  );
}
