import { useState } from 'react';
import { TextInput, View } from 'react-native';
import { Button } from '@/components/button';
import { Choice } from '@/components/controls';
import { Row } from '@/components/list';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { validEmergencyNumber } from '@/state/emergency-settings';
import { useSettings } from '@/state/settings';
import { radius, spacing, touch, type, useTheme } from '@/theme';

export function EmergencyNumber() {
  const t = useT();
  const number = useSettings((s) => s.emergencyNumber);
  const seconds = useSettings((s) => s.sosCountdownSeconds);
  const set = useSettings((s) => s.set);
  const [custom, setCustom] = useState(number !== '123' && number !== '112');
  return <>
    <Row label={t('settings.emergencyNumber')} right={<Choice label={t('settings.emergencyNumber')}
      value={custom ? 'custom' : number} options={[
        { value: '123', label: '123' }, { value: '112', label: '112' },
        { value: 'custom', label: t('settings.customNumber') },
      ]} onChange={(value) => { setCustom(value === 'custom'); if (value !== 'custom') set({ emergencyNumber: value }); }} />} />
    {custom ? <CustomNumber key={number} number={number} /> : null}
    <Row label={t('settings.countdown')} right={<Choice label={t('settings.countdown')}
      value={String(seconds)} options={([30, 45, 60] as const).map((value) => ({ value: String(value), label: `${value} seconds` }))}
      onChange={(value) => set({ sosCountdownSeconds: Number(value) as 30 | 45 | 60 })} />} />
  </>;
}

function CustomNumber({ number }: { number: string }) {
  const t = useT();
  const { colors } = useTheme();
  const [draft, setDraft] = useState(number);
  const set = useSettings((s) => s.set);
  return <View style={{ padding: spacing.lg, gap: spacing.sm }}>
    <TextInput value={draft} onChangeText={setDraft} keyboardType="phone-pad"
      accessibilityLabel={t('settings.customNumber')} autoCorrect={false}
      style={[type.body, { minHeight: touch.min, paddingHorizontal: spacing.md,
        borderRadius: radius.sm, backgroundColor: colors.surfaceRaised, color: colors.text }]} />
    <Text variant="caption" tone="secondary">{t('settings.numberHint')}</Text>
    <Button title={t('settings.saveNumber')} disabled={!validEmergencyNumber(draft) || draft === number}
      onPress={() => set({ emergencyNumber: draft })} />
  </View>;
}
