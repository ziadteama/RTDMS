import * as Haptics from 'expo-haptics';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { BackHandler, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/button';
import { Row, Section } from '@/components/list';
import { ProgressBar } from '@/components/progress-bar';
import { Text } from '@/components/text';
import { useT, type StringKey } from '@/i18n';
import { announceCountdown, cancelSos, runEmergency, type CallProgressState } from '@/services/emergency';
import type { ChannelStatus } from '@/services/relay/types';
import type { ContactChannelState } from '@/services/sos-channels';
import { db } from '@/state/db';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';
import { spacing, useTheme } from '@/theme';

type Phase = { kind: 'countdown' } | { kind: 'active' } | { kind: 'cancelled' };
type TFn = (key: StringKey, params?: Record<string, string | number>) => string;

function formatWhatsappStatus(status: ChannelStatus, t: TFn): string {
  if (status === 'queued') return t('sos.status.waiting');
  if (status === 'unknown') return t('sos.status.no_data');
  return t(`sos.status.${status}`);
}

function formatSmsStatus(status: ChannelStatus, t: TFn): string {
  if (status === 'queued') return t('sos.status.waiting');
  if (status === 'delivered') return t('sos.status.delivered');
  if (status === 'failed') return t('sos.status.failed');
  return t('sos.status.sent');
}

export default function Sos() {
  const t = useT();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { incident } = useLocalSearchParams<{ incident: string }>();
  const id = Number(incident);
  const kind = db.getIncident(id)?.kind ?? 'manual';
  const countdown = useSettings((s) => s.sosCountdownSeconds);
  const total = kind === 'manual' ? 10 : countdown;
  const [left, setLeft] = useState<number>(total);
  const [phase, setPhase] = useState<Phase>({ kind: 'countdown' });
  const [callState, setCallState] = useState<CallProgressState>('none');
  const [callNumber, setCallNumber] = useState('');
  const [smsSent, setSmsSent] = useState<number>(0);
  const [channels, setChannels] = useState<ContactChannelState[]>([]);
  const fired = useRef(false);
  const hasContacts = useSecure((s) => s.contacts.length > 0);

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => true);
    return () => sub.remove();
  }, []);

  useEffect(() => {
    announceCountdown(total);
  }, [total]);

  const send = () => {
    if (fired.current) return;
    fired.current = true;
    setPhase({ kind: 'active' });
    void runEmergency(id, (_step, info) => {
      if (info.contacts) setChannels(info.contacts);
      if (info.sent !== undefined) setSmsSent(info.sent);
      if (info.number) setCallNumber(info.number);
      if (info.callState) setCallState(info.callState);
    });
  };

  const expire = useEffectEvent(() => send());
  const tick = useEffectEvent(() => {
    setLeft((s) => s - 1);
    if (process.env.EXPO_OS !== 'web') void Haptics.impactAsync(left <= 10 ? Haptics.ImpactFeedbackStyle.Heavy : Haptics.ImpactFeedbackStyle.Medium);
    if (left - 1 === 10) announceCountdown(10);
  });

  useEffect(() => {
    if (phase.kind !== 'countdown') return;
    if (left <= 0) {
      expire();
      return;
    }
    const timer = setTimeout(tick, 1000);
    return () => clearTimeout(timer);
  }, [left, phase.kind]);

  const ok = () => {
    cancelSos(id);
    setPhase({ kind: 'cancelled' });
    router.back();
  };

  const bg = phase.kind === 'countdown' ? colors.alert.max : colors.background;
  const fg = phase.kind === 'countdown' ? colors.onAlert.max : colors.text;

  return (
    <View
      style={{
        flex: 1,
        backgroundColor: bg,
        paddingTop: insets.top + spacing.xl,
        paddingBottom: insets.bottom + spacing.xl,
        paddingHorizontal: spacing.xl,
        gap: spacing.xl,
      }}
      accessibilityViewIsModal
    >
      <Text variant="title" color={fg} accessibilityRole="header">
        {kind === 'crash' ? t('sos.crash') : t('sos.manual')}
      </Text>
      {phase.kind === 'countdown' ? (
        <>
          <View style={{ flex: 1, justifyContent: 'center', gap: spacing.lg }}>
            <Text variant="headline" color={fg}>
              {t('sos.sendingIn')}
            </Text>
            <Text variant="countdown" color={fg} accessibilityLiveRegion="assertive" accessibilityLabel={`${left}`}>
              {left}
            </Text>
            <ProgressBar durationMs={total * 1000} running color={fg} height={spacing.sm} />
          </View>
          <Button title={t('sos.ok')} size="xl" variant="primary" onPress={ok} />
          <Button title={t('sos.sendNow')} variant="ghost" onPress={send} />
        </>
      ) : null}
      {phase.kind === 'active' ? (
        <ScrollView contentContainerStyle={{ gap: spacing.xl, paddingBottom: spacing.lg }} showsVerticalScrollIndicator={false}>
          <Text variant="headline">{t('sos.done')}</Text>
          <View style={{ gap: spacing.xs }}>
            <Text tone="secondary">
              {!hasContacts
                ? t('sos.noContacts')
                : smsSent === 1
                ? t('sos.smsSentSingle')
                : t('sos.smsSentPlural', { n: smsSent })}
            </Text>
            {callState === 'waiting' ? (
              <View style={{ gap: spacing.sm, marginTop: spacing.xs }}>
                <Text tone="secondary">{t('sos.callDelay', { n: callNumber })}</Text>
                <Button title={t('sos.cancelCall')} onPress={ok} />
              </View>
            ) : null}
            {callState === 'starting' ? (
              <Text tone="secondary" accessibilityLiveRegion="assertive">
                {t('sos.callStarting', { n: callNumber })}
              </Text>
            ) : null}
            {callState === 'calling' ? (
              <Text tone="secondary" accessibilityLiveRegion="assertive">
                {t('sos.callDialed', { n: callNumber })}
              </Text>
            ) : null}
            {callState === 'failed' ? (
              <Text tone="secondary" accessibilityLiveRegion="assertive">
                {t('sos.callFailed')}
              </Text>
            ) : null}
          </View>
          {channels.length > 0 ? (
            <Section title={t('settings.contacts')}>
              {channels.map((c) => (
                <Row
                  key={c.id}
                  icon="person"
                  label={c.name}
                  detail={`${t('sos.whatsapp')}: ${formatWhatsappStatus(c.whatsapp, t)}\n${t('sos.sms')}: ${formatSmsStatus(c.sms, t)}`}
                />
              ))}
            </Section>
          ) : null}
          <Button title={t('sos.close')} size="lg" onPress={() => router.back()} />
        </ScrollView>
      ) : null}
    </View>
  );
}
