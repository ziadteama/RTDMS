/**
 * Phone-side alert output. Input: fusion's AlertPattern from GET /alert, nothing else. When the
 * pattern escalates the phone vibrates, speaks an English line (en-US) and, if the app is not on
 * screen, posts a notification — at the same moment the Pi's buzzer sounds.
 */
import * as Haptics from 'expo-haptics';
import * as Speech from 'expo-speech';
import { AppState, Platform, Vibration } from 'react-native';

import SahiNative from '@modules/sahi-native';
import { t, type StringKey } from '@/i18n';
import { ALERT_PRESENTATION, driverState, isEscalation, voiceKey, type HapticKind } from '@/pi/alert';
import type { AlertPattern } from '@/pi/types';
import { useLive } from '@/state/live';
import { useSettings } from '@/state/settings';

const NOTIFICATION_ID = 1001;

export function haptic(kind: HapticKind, pattern: AlertPattern): void {
  const v = useSettings.getState().vibration;
  if (v === 'off' || kind === 'none' || Platform.OS === 'web') return;
  if (v === 'light') {
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    return;
  }
  if (kind === 'tap') void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
  else
    void Haptics.notificationAsync(
      kind === 'warning' ? Haptics.NotificationFeedbackType.Warning : Haptics.NotificationFeedbackType.Error,
    );
  // Strong: a longer motor pattern for the alarms the report pairs with vibration.
  if (pattern === 'continuous' || pattern === 'max') Vibration.vibrate([0, 350, 150, 350, 150, 350]);
}

export function speak(key: StringKey, params?: Record<string, string | number>): void {
  const { sound, volume } = useSettings.getState();
  if (!sound) return;
  Speech.stop();
  Speech.speak(t(key, params), { language: 'en-US', volume, rate: 1.0 });
}

function present(pattern: AlertPattern): void {
  const p = ALERT_PRESENTATION[pattern];
  haptic(p.haptic, pattern);
  const live = useLive.getState();
  const key = voiceKey(pattern, driverState(live.status, live.connection === 'online'));
  if (p.voice && key) speak(key as StringKey);
  if (p.notify && AppState.currentState !== 'active' && SahiNative) {
    const reasons = live.alert?.reasons.join(', ') ?? '';
    SahiNative.notify(NOTIFICATION_ID, 'alerts', t(`pattern.${pattern}`), reasons || (key ? t(key as StringKey) : ''), null);
  }
}

export function startAlertEngine(): () => void {
  let last: AlertPattern | null = null;
  let repeat: ReturnType<typeof setInterval> | null = null;

  const unsub = useLive.subscribe((s) => {
    const pattern: AlertPattern | null = s.connection === 'online' ? (s.alert?.pattern ?? null) : null;
    if (pattern === last) return;
    if (repeat) clearInterval(repeat);
    repeat = null;
    if (pattern && isEscalation(last, pattern)) present(pattern);
    if (pattern && pattern !== 'none') {
      const ms = ALERT_PRESENTATION[pattern].repeatMs;
      if (ms) repeat = setInterval(() => present(pattern), ms);
    } else if (SahiNative) {
      SahiNative.cancel(NOTIFICATION_ID);
    }
    last = pattern;
  });
  return () => {
    unsub();
    if (repeat) clearInterval(repeat);
    Speech.stop();
  };
}
