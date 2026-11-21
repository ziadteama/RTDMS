import * as Haptics from 'expo-haptics';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { BackHandler, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button } from '@/components/button';
import { ProgressBar } from '@/components/progress-bar';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { COUNTDOWN_S, announceCountdown, cancelSos, runEmergency } from '@/services/emergency';
import { db } from '@/state/db';
import { useSecure } from '@/state/secure';
import { spacing, useTheme } from '@/theme';

type Phase = { kind: 'countdown' } | { kind: 'sending'; line: string } | { kind: 'done'; lines: string[] } | { kind: 'cancelled' };

/**
 * Full-screen countdown. "I'm OK" is the largest target on screen. The countdown is the one place
 * the app animates continuously: a linear bar (time passing) plus a haptic tick every second.
 */
export default function Sos() {
  const t = useT();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { incident } = useLocalSearchParams<{ incident: string }>();
  const id = Number(incident);
  const kind = db.getIncident(id)?.kind ?? 'manual';
  const total = COUNTDOWN_S[kind];
  const [left, setLeft] = useState<number>(total);
  const [phase, setPhase] = useState<Phase>({ kind: 'countdown' });
  const fired = useRef(false);
  const hasContacts = useSecure((s) => s.contacts.length > 0);

  // Android back must not dismiss the countdown by accident: only "I'm OK" cancels.
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
    const lines: string[] = [];
    setPhase({ kind: 'sending', line: t('sos.sending') });
    void runEmergency(id, (step, info) => {
      if (step === 'sms' && info.sent !== undefined) lines.push(hasContacts ? (info.sent ? t('sos.smsSent', { n: info.sent }) : t('sos.smsFailed')) : t('sos.noContacts'));
      if (step === 'call') setPhase({ kind: 'sending', line: t('sos.calling', { n: info.number ?? '' }) });
      if (step === 'call' && info.number) lines.push(t('sos.calling', { n: info.number }));
      if (step === 'done') setPhase({ kind: 'done', lines });
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

  const bg = phase.kind === 'countdown' || phase.kind === 'sending' ? colors.alert.max : colors.background;
  const fg = phase.kind === 'countdown' || phase.kind === 'sending' ? colors.onAlert.max : colors.text;
  return (
    <View
      style={{ flex: 1, backgroundColor: bg, paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl, paddingHorizontal: spacing.xl, gap: spacing.xl }}
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
            <ProgressBar durationMs={total * 1000} running color={fg} height={10} />
          </View>
          <Button title={t('sos.ok')} size="xl" variant="primary" onPress={ok} />
          <Button title={t('sos.sendNow')} variant="ghost" onPress={send} />
        </>
      ) : null}
      {phase.kind === 'sending' ? (
        <View style={{ flex: 1, justifyContent: 'center' }}>
          <Text variant="title" color={fg} accessibilityLiveRegion="assertive">
            {phase.line}
          </Text>
        </View>
      ) : null}
      {phase.kind === 'done' ? (
        <>
          <View style={{ flex: 1, justifyContent: 'center', gap: spacing.md }}>
            <Text variant="title">{t('sos.done')}</Text>
            {phase.lines.map((l) => (
              <Text key={l} tone="secondary" selectable>
                {l}
              </Text>
            ))}
          </View>
          <Button title={t('sos.close')} size="lg" onPress={() => router.back()} />
        </>
      ) : null}
    </View>
  );
}
