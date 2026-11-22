import { useState } from 'react';
import { TextInput, View } from 'react-native';

import { Button } from '@/components/button';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { BLE_TOKEN_MIN, validBleName, validBleToken } from '@/pi/parse';
import { radius, spacing, touch, type, useTheme } from '@/theme';

/**
 * Secondary, collapsed entry for pairing without a QR code: the unit's Bluetooth name and the
 * pairing code printed on its setup page (dev and support use; the QR is the main path).
 */
export function PairBleManual({
  busy,
  onSubmit,
  onInvalid,
}: {
  busy: boolean;
  onSubmit: (ble: { name: string; token: string }) => void;
  onInvalid: () => void;
}) {
  const t = useT();
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [token, setToken] = useState('');

  if (!open) return <Button title={t('onb.pair.bleOpen')} variant="ghost" onPress={() => setOpen(true)} accessibilityHint={t('onb.pair.bleHint')} />;

  const submit = () => {
    const n = validBleName(name);
    const k = validBleToken(token);
    if (n && k) onSubmit({ name: n, token: k });
    else onInvalid();
  };
  const input = [
    type.body,
    { minHeight: touch.min, paddingHorizontal: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surface, color: colors.text, writingDirection: 'ltr' as const, textAlign: 'left' as const },
  ];
  return (
    <View style={{ gap: spacing.md }}>
      <Text variant="label" tone="secondary">
        {t('onb.pair.bleTitle')}
      </Text>
      <TextInput
        value={name}
        onChangeText={setName}
        autoCapitalize="none"
        autoCorrect={false}
        placeholder={t('onb.pair.bleName')}
        placeholderTextColor={colors.textTertiary}
        accessibilityLabel={t('onb.pair.bleName')}
        style={input}
      />
      <TextInput
        value={token}
        onChangeText={setToken}
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
        placeholder={t('onb.pair.bleCode', { min: BLE_TOKEN_MIN })}
        placeholderTextColor={colors.textTertiary}
        accessibilityLabel={t('onb.pair.bleCode', { min: BLE_TOKEN_MIN })}
        style={input}
      />
      <Button title={t('onb.pair.bleConnect')} icon="bluetooth" variant="secondary" onPress={submit} loading={busy} />
    </View>
  );
}
