import { router } from 'expo-router';
import { useState } from 'react';
import { TextInput, View } from 'react-native';
import { useShallow } from 'zustand/react/shallow';

import { useLinkRows } from './link-row';

import { Row, Section } from '@/components/list';
import { Text } from '@/components/text';
import { Toggle } from '@/components/controls';
import { dx } from '@/i18n/diagnostics';
import { normalizeBaseUrl } from '@/pi/parse';
import { simulateCrash } from '@/services/monitor';
import { useSettings } from '@/state/settings';
import { radius, spacing, touch, type, useTheme } from '@/theme';

export function ConnectionDiag() {
  const { colors } = useTheme();
  const s = useSettings(
    useShallow((x) => ({
      baseUrl: x.baseUrl,
      demo: x.demo,
      relayUrl: x.relayUrl ?? '',
      relayKey: x.relayKey ?? '',
    })),
  );
  const set = useSettings((x) => x.set);
  const linkRows = useLinkRows();

  const [addressDraft, setAddressDraft] = useState(s.baseUrl);
  const [addressBad, setAddressBad] = useState(false);
  const [relayUrlDraft, setRelayUrlDraft] = useState(s.relayUrl);
  const [relayKeyDraft, setRelayKeyDraft] = useState(s.relayKey);

  const commitAddress = () => {
    const url = normalizeBaseUrl(addressDraft);
    setAddressBad(!url);
    if (url && url !== s.baseUrl) set({ baseUrl: url });
  };

  const commitRelay = () => {
    set({
      relayUrl: relayUrlDraft.trim() || undefined,
      relayKey: relayKeyDraft.trim() || undefined,
    });
  };

  const inputStyle = [
    type.body,
    {
      minHeight: touch.min,
      paddingHorizontal: spacing.md,
      borderRadius: radius.sm,
      backgroundColor: colors.surfaceRaised,
      color: colors.text,
      writingDirection: 'ltr' as const,
      textAlign: 'left' as const,
    },
  ];

  return (
    <Section title={dx('diag.section.connection')} footer={s.demo ? dx('diag.conn.demoFooter') : undefined}>
      <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm }}>
        <Text>{dx('diag.conn.address')}</Text>
        <TextInput
          value={addressDraft}
          onChangeText={setAddressDraft}
          onEndEditing={commitAddress}
          onSubmitEditing={commitAddress}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          editable={!s.demo}
          accessibilityLabel={dx('diag.conn.address')}
          style={[inputStyle, { opacity: s.demo ? 0.45 : 1 }]}
        />
        {addressBad ? (
          <Text variant="caption" tone="secondary">
            {dx('diag.conn.badUrl')}
          </Text>
        ) : null}
      </View>
      {linkRows}
      <Row label={dx('diag.conn.pair')} icon="qr" chevron onPress={() => router.push('/pair')} />
      <Row label={dx('diag.conn.demo')} icon="play" right={<Toggle label={dx('diag.conn.demo')} value={s.demo} onChange={(v) => set({ demo: v })} />} />
      {s.demo ? <Row label={dx('diag.conn.fakeCrash')} icon="crash" chevron onPress={simulateCrash} /> : null}
      <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm }}>
        <Text>{dx('diag.conn.relayUrl')}</Text>
        <TextInput
          value={relayUrlDraft}
          onChangeText={setRelayUrlDraft}
          onEndEditing={commitRelay}
          onSubmitEditing={commitRelay}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          accessibilityLabel={dx('diag.conn.relayUrl')}
          style={inputStyle}
        />
      </View>
      <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm }}>
        <Text>{dx('diag.conn.relayKey')}</Text>
        <TextInput
          value={relayKeyDraft}
          onChangeText={setRelayKeyDraft}
          onEndEditing={commitRelay}
          onSubmitEditing={commitRelay}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          accessibilityLabel={dx('diag.conn.relayKey')}
          style={inputStyle}
        />
      </View>
    </Section>
  );
}
