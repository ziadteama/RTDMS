import { useState } from 'react';
import { TextInput, View } from 'react-native';

import { Button } from '@/components/button';
import { Row, Section } from '@/components/list';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { isValidPhone, normalizeE164 } from '@/services/phone';
import { syncRelayContacts } from '@/services/relay/contacts';
import { useSecure, type Contact } from '@/state/secure';
import { useSettings } from '@/state/settings';
import { radius, spacing, touch, type, useTheme } from '@/theme';

const MAX = 5;

function ContactField({
  value,
  onChange,
  label,
  phone,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  phone?: boolean;
}) {
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

export function ContactsRelayEditor() {
  const t = useT();
  const contacts = useSecure((s) => s.contacts);
  const setContacts = useSecure((s) => s.setContacts);
  const driverName = useSettings((s) => s.driverName ?? 'Driver');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState<string | null>(null);

  const sync = (updated: Contact[]) => {
    setContacts(updated);
    void syncRelayContacts(driverName, updated).then((synced) => {
      setContacts(synced);
    });
  };

  const add = () => {
    const normalized = normalizeE164(phone);
    if (!name.trim() || !isValidPhone(normalized)) {
      setError(t('contacts.invalid'));
      return;
    }
    const newContact: Contact = {
      id: `${Date.now()}`,
      name: name.trim(),
      phone: normalized,
      relayStatus: 'pending',
    };
    const updated = [...contacts, newContact];
    setName('');
    setPhone('');
    setError(null);
    sync(updated);
  };

  const remove = (id: string) => {
    const updated = contacts.filter((c) => c.id !== id);
    sync(updated);
  };

  return (
    <View style={{ gap: spacing.xl }}>
      <Text variant="caption" tone="secondary">
        {t('contacts.consentNote')}
      </Text>
      <Section footer={t('contacts.max')}>
        {contacts.length === 0 ? <Row label={t('contacts.empty')} /> : null}
        {contacts.map((c) => (
          <Row
            key={c.id}
            icon="person"
            label={c.name}
            detail={`${c.phone} • ${t(`contacts.status.${c.relayStatus ?? 'pending'}`)}`}
            right={<Button title={t('contacts.remove')} variant="ghost" onPress={() => remove(c.id)} />}
          />
        ))}
      </Section>
      {contacts.length < MAX ? (
        <View style={{ gap: spacing.md }}>
          <ContactField value={name} onChange={setName} label={t('contacts.name')} />
          <ContactField value={phone} onChange={setPhone} label={t('contacts.phone')} phone />
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
