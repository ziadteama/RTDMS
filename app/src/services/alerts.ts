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
import { ALERT_PRESENTATION, driverState, voiceKey, type HapticKind } from '@/pi/alert';
import type { AlertPattern } from '@/pi/types';
import { useLive } from '@/state/live';
import { useSettings } from '@/state/settings';

import { decideAlert, initialAlertState, repeatVoice } from './alert-policy';

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

let speechRequest = 0;
function stopSpeech(): void {
  speechRequest += 1;
  void Speech.stop().catch(() => undefined);
}

export function speak(key: StringKey, params?: Record<string, string | number>): void {
  const { sound, volume } = useSettings.getState();
  if (!sound) return;
  const request = ++speechRequest;
  void Speech.stop().then(() => {
    if (request === speechRequest) Speech.speak(t(key, params), { language: 'en-US', volume, rate: 1.0 });
  }).catch(() => undefined);
}

function present(pattern: AlertPattern, voice = true, notify = true): void {
  const p = ALERT_PRESENTATION[pattern];
  haptic(p.haptic, pattern);
  const live = useLive.getState();
  const key = voiceKey(pattern, driverState(live.status, live.connection === 'online'));
  if (voice && p.voice && key) speak(key as StringKey);
  if (notify && p.notify && AppState.currentState !== 'active' && SahiNative) {
    const reasons = live.alert?.reasons.join(', ') ?? '';
    SahiNative.notify(NOTIFICATION_ID, 'alerts', t(`pattern.${pattern}`), reasons || (key ? t(key as StringKey) : ''), null);
  }
}

export function startAlertEngine(): () => void {
  let state = initialAlertState;
  let muted = false;
  let repeat: ReturnType<typeof setInterval> | null = null;
  const clearRepeat = () => { if (repeat) clearInterval(repeat); repeat = null; };
  const stop = () => { stopSpeech(); SahiNative?.cancel(NOTIFICATION_ID); };
  const update = () => {
    const s = useLive.getState();
    const pattern = !s.calibrating && s.connection === 'online' ? (s.alert?.pattern ?? null) : null;
    const decision = decideAlert(state, pattern, pattern ? (s.alert?.episode ?? null) : null, Date.now());
    if (s.calibrating && !muted) stop();
    muted = s.calibrating;
    state = decision.state;
    if (!decision.changed) return;
    clearRepeat();
    if (decision.stop && !muted) stop();
    if (decision.present && pattern) present(pattern);
    const ms = pattern ? ALERT_PRESENTATION[pattern].repeatMs : null;
    if (ms && pattern) repeat = setInterval(() => {
      const voice = repeatVoice(state, Date.now());
      if (voice) state = { ...state, voicedAt: Date.now() };
      present(pattern, voice, false);
    }, ms);
  };
  const unsub = useLive.subscribe(update);
  update();
  return () => { unsub(); clearRepeat(); stop(); };
}
