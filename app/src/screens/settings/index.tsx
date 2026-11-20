import { reloadAppAsync } from 'expo';
import Constants from 'expo-constants';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, TextInput, View } from 'react-native';
import { useShallow } from 'zustand/react/shallow';

import { Button } from '@/components/button';
import { Choice, SliderControl, Toggle } from '@/components/controls';
import { Row, Section } from '@/components/list';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { normalizeBaseUrl } from '@/pi/parse';
import { ALERT_PATTERNS, type AlertPattern, type PiSettings, type Sensitivity } from '@/pi/types';
import { useLive } from '@/state/live';
import { useSecure } from '@/state/secure';
import { useSettings, type Language, type ThemeSetting, type Units, type Vibration } from '@/state/settings';
import { clearKv } from '@/state/storage';
import { haptic, speak } from '@/services/alerts';
import { pi } from '@/services/pi';
import { ALERT_PRESENTATION } from '@/pi/alert';
import { radius, spacing, touch, type, useTheme } from '@/theme';

import { usePiSettings } from './use-pi-settings';

function SliderRow({ label, value, unit, min, max, step, onChange, disabled }: { label: string; value: number; unit: string; min: number; max: number; step: number; onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm, opacity: disabled ? 0.45 : 1 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <Text>{label}</Text>
        <Text tone="secondary" style={{ fontVariant: ['tabular-nums'] }}>
          {value.toFixed(1)} {unit}
        </Text>
      </View>
      <SliderControl value={value} min={min} max={max} step={step} onChange={onChange} disabled={disabled} />
    </View>
  );
}

function PiDetection() {
  const t = useT();
  const online = useLive((s) => s.connection === 'online');
  const { state, update } = usePiSettings();
  const ready = state.kind === 'ready' && online;
  const v: PiSettings | null = state.kind === 'ready' ? state.value : null;
  const footer = !online ? t('settings.offlineFooter') : state.kind === 'unsupported' ? t('banner.noAlertApi') : t('settings.detectionFooter');
  return (
    <>
      <Section title={t('settings.driver')}>
        <Row
          label={t('settings.profile')}
          disabled={!ready}
          right={
            v ? (
              <Choice label={t('settings.profile')} value={v.profile} options={v.profiles.map((p) => ({ value: p, label: p }))} onChange={(p) => update({ profile: p })} disabled={!ready} />
            ) : undefined
          }
        />
        <Row label={t('settings.calibrate')} icon="eye" chevron disabled={!online} onPress={() => router.push('/calibrate')} />
      </Section>
      <Section title={t('settings.detection')} footer={footer}>
        <Row
          label={t('settings.sensitivity')}
          disabled={!ready}
          right={
            v ? (
              <Choice<Sensitivity>
                label={t('settings.sensitivity')}
                value={v.sensitivity}
                options={(['low', 'normal', 'high'] as const).map((s) => ({ value: s, label: t(`settings.sens.${s}`) }))}
                onChange={(s) => update({ sensitivity: s })}
                disabled={!ready}
              />
            ) : undefined
          }
        />
        <SliderRow label={t('settings.eyeClosure')} value={v?.eye_closure_s ?? 2} unit={t('live.s')} min={0.5} max={5} step={0.5} onChange={(x) => update({ eye_closure_s: x })} disabled={!ready} />
        <SliderRow label={t('settings.offroad')} value={v?.offroad_gaze_s ?? 2} unit={t('live.s')} min={0.5} max={5} step={0.5} onChange={(x) => update({ offroad_gaze_s: x })} disabled={!ready} />
        <SliderRow label={t('settings.phoneDuration')} value={v?.phone_s ?? 1} unit={t('live.s')} min={0.5} max={5} step={0.5} onChange={(x) => update({ phone_s: x })} disabled={!ready} />
        {(['drowsiness', 'distraction', 'phone', 'physiology'] as const).map((d) => (
          <Row
            key={d}
            label={t(`settings.det.${d}`)}
            disabled={!ready}
            right={<Toggle label={t(`settings.det.${d}`)} value={v?.detectors[d] ?? true} disabled={!ready} onChange={(on) => update({ detectors: { [d]: on } as PiSettings['detectors'] })} />}
          />
        ))}
      </Section>
    </>
  );
}

function PhoneAlerts() {
  const t = useT();
  const s = useSettings(useShallow((x) => ({ sound: x.sound, volume: x.volume, vibration: x.vibration })));
  const set = useSettings((x) => x.set);
  const online = useLive((x) => x.connection === 'online');
  const [pattern, setPattern] = useState<AlertPattern>('repeated');
  const [sent, setSent] = useState(false);
  return (
    <Section title={t('settings.alerts')}>
      <Row label={t('settings.sound')} right={<Toggle label={t('settings.sound')} value={s.sound} onChange={(v) => set({ sound: v })} />} />
      <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm, opacity: s.sound ? 1 : 0.45 }}>
        <Text>{t('settings.volume')}</Text>
        <SliderControl value={s.volume} min={0.1} max={1} step={0.1} onChange={(v) => set({ volume: v })} disabled={!s.sound} />
      </View>
      <Row
        label={t('settings.vibration')}
        right={
          <Choice<Vibration>
            label={t('settings.vibration')}
            value={s.vibration}
            options={(['off', 'light', 'strong'] as const).map((v) => ({ value: v, label: t(`settings.vib.${v}`) }))}
            onChange={(v) => set({ vibration: v })}
          />
        }
      />
      <Row
        label={t('settings.testPattern')}
        right={
          <Choice<AlertPattern>
            label={t('settings.testPattern')}
            value={pattern}
            options={ALERT_PATTERNS.filter((p) => p !== 'none').map((p) => ({ value: p, label: t(`pattern.${p}`) }))}
            onChange={setPattern}
          />
        }
      />
      <View style={{ padding: spacing.lg }}>
        <Button
          title={sent ? t('health.sent') : t('settings.testAlert')}
          icon="notifications"
          variant="secondary"
          disabled={!online}
          onPress={() => {
            // The Pi buzzes this pattern (POST /test_alert) and reports it on /alert, so the phone's
            // alert engine is exercised end to end. A Pi without /test_alert: local output only.
            pi()
              .send('POST', '/test_alert', { pattern })
              .then(
                () => setSent(true),
                () => {
                  haptic(ALERT_PRESENTATION[pattern].haptic, pattern);
                  speak('voice.test');
                },
              );
            setTimeout(() => setSent(false), 2000);
          }}
        />
      </View>
    </Section>
  );
}

function Connection() {
  const t = useT();
  const { colors } = useTheme();
  const s = useSettings(useShallow((x) => ({ baseUrl: x.baseUrl, demo: x.demo })));
  const set = useSettings((x) => x.set);
  const [draft, setDraft] = useState(s.baseUrl);
  const [bad, setBad] = useState(false);
  const commit = () => {
    const url = normalizeBaseUrl(draft);
    setBad(!url);
    if (url && url !== s.baseUrl) set({ baseUrl: url });
  };
  return (
    <Section title={t('settings.connection')} footer={s.demo ? t('settings.demoFooter') : undefined}>
      <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm }}>
        <Text>{t('settings.address')}</Text>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          onEndEditing={commit}
          onSubmitEditing={commit}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          editable={!s.demo}
          accessibilityLabel={t('settings.address')}
          style={[type.body, { minHeight: touch.min, paddingHorizontal: spacing.md, borderRadius: radius.sm, backgroundColor: colors.surfaceRaised, color: colors.text, writingDirection: 'ltr', textAlign: 'left', opacity: s.demo ? 0.45 : 1 }]}
        />
        {bad ? (
          <Text variant="caption" tone="secondary">
            {t('onb.pair.badUrl')}
          </Text>
        ) : null}
      </View>
      <Row label={t('settings.pair')} icon="qr" chevron onPress={() => router.push('/pair')} />
      <Row label={t('settings.demo')} icon="play" right={<Toggle label={t('settings.demo')} value={s.demo} onChange={(v) => set({ demo: v })} />} />
    </Section>
  );
}

function AppPrefs() {
  const t = useT();
  const s = useSettings(useShallow((x) => ({ language: x.language, units: x.units, theme: x.theme })));
  const set = useSettings((x) => x.set);
  return (
    <Section title={t('settings.app')}>
      <Row
        label={t('settings.language')}
        right={
          <Choice<Language>
            label={t('settings.language')}
            value={s.language}
            options={[
              { value: 'en', label: 'English' },
              { value: 'ar', label: 'العربية' },
            ]}
            onChange={(v) => set({ language: v })}
          />
        }
      />
      <Row
        label={t('settings.units')}
        right={<Choice<Units> label={t('settings.units')} value={s.units} options={[{ value: 'kmh', label: t('common.kmh') }, { value: 'mph', label: t('common.mph') }]} onChange={(v) => set({ units: v })} />}
      />
      <Row
        label={t('settings.theme')}
        right={
          <Choice<ThemeSetting>
            label={t('settings.theme')}
            value={s.theme}
            options={(['dark', 'light', 'system'] as const).map((v) => ({ value: v, label: t(`settings.theme.${v}`) }))}
            onChange={(v) => set({ theme: v })}
          />
        }
      />
    </Section>
  );
}

function Privacy() {
  const t = useT();
  const paused = useSettings((x) => x.paused);
  const set = useSettings((x) => x.set);
  const deleteAll = () =>
    Alert.alert(t('settings.deleteAll'), t('settings.deleteConfirm'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('common.delete'),
        style: 'destructive',
        onPress: () => {
          useSecure.getState().wipe();
          useSettings.getState().reset();
          clearKv();
          void reloadAppAsync('all data deleted');
        },
      },
    ]);
  return (
    <Section title={t('settings.privacy')} footer={t('settings.pauseFooter')}>
      <Row label={t('settings.pause')} icon="pause" right={<Toggle label={t('settings.pause')} value={paused} onChange={(v) => set({ paused: v })} />} />
      <Row label={t('settings.whatStored')} icon="info" chevron onPress={() => router.push('/privacy')} />
      <Row label={t('settings.deleteAll')} icon="delete" destructive onPress={deleteAll} />
    </Section>
  );
}

export function Settings() {
  const t = useT();
  return (
    <Screen>
      <PiDetection />
      <PhoneAlerts />
      <Connection />
      <AppPrefs />
      <Privacy />
      <Section>
        <Row label={t('settings.version')} value={Constants.expoConfig?.version ?? '—'} />
      </Section>
    </Screen>
  );
}

