import { useState } from 'react';
import { TextInput, View } from 'react-native';

import { Button } from '@/components/button';
import { Row, Section } from '@/components/list';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { useSecure } from '@/state/secure';
import { radius, spacing, touch, type, useTheme } from '@/theme';

const MAX = 5;

function Field({ value, onChange, label, phone }: { value: string; onChange: (v: string) => void; label: string; phone?: boolean }) {
  const { colors } = useTheme();
  return (
    <TextInput
      value={value}
      onChangeText={onChange}
      placeholder={label}
      accessibilityLabel={label}
      placeholderTextColor={colors.textTertiary}
      keyboardType={phone ? 'phone-pad' : 'default'}
      autoComplete={phone ? 'tel' : 'name'}
      textContentType={phone ? 'telephoneNumber' : 'name'}
      style={[
        type.body,
        {
          minHeight: touch.min,
          paddingHorizontal: spacing.lg,
          borderRadius: radius.md,
          borderCurve: 'continuous',
          backgroundColor: colors.surface,
          color: colors.text,
          textAlign: 'auto',
        },
      ]}
    />
  );
}

/** Emergency contacts: stored with expo-secure-store (Android Keystore), never leave the phone. */
export function ContactsEditor() {
  const t = useT();
  const contacts = useSecure((s) => s.contacts);
  const setContacts = useSecure((s) => s.setContacts);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState<string | null>(null);

  const add = () => {
    const p = phone.replace(/[^\d+]/g, '');
    if (!name.trim() || p.length < 3) {
      setError(t('contacts.invalid'));
      return;
    }
    setContacts([...contacts, { id: `${Date.now()}`, name: name.trim(), phone: p }]);
    setName('');
    setPhone('');
    setError(null);
  };

  return (
    <View style={{ gap: spacing.xl }}>
      <Section footer={t('contacts.max')}>
        {contacts.length === 0 ? <Row label={t('contacts.empty')} /> : null}
        {contacts.map((c) => (
          <Row
            key={c.id}
            icon="person"
            label={c.name}
            detail={c.phone}
            right={<Button title={t('contacts.remove')} variant="ghost" onPress={() => setContacts(contacts.filter((x) => x.id !== c.id))} />}
          />
        ))}
      </Section>
      {contacts.length < MAX ? (
        <View style={{ gap: spacing.md }}>
          <Field value={name} onChange={setName} label={t('contacts.name')} />
          <Field value={phone} onChange={setPhone} label={t('contacts.phone')} phone />
          {error ? (
            <Text variant="caption" tone="secondary" accessibilityLiveRegion="polite" selectable>
              {error}
            </Text>
          ) : null}
          <Button title={t('contacts.add')} icon="add" variant="secondary" onPress={add} />
        </View>
      ) : null}
    </View>
  );
}
