import { useState } from 'react';
import { View } from 'react-native';
import { useShallow } from 'zustand/react/shallow';

import { Button } from '@/components/button';
import { Choice, SliderControl, Toggle } from '@/components/controls';
import { Row, Section } from '@/components/list';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { ALERT_PRESENTATION } from '@/pi/alert';
import type { Sensitivity } from '@/pi/types';
import { haptic, speak } from '@/services/alerts';
import { pi } from '@/services/pi';
import { useLive } from '@/state/live';
import { useSettings, type Vibration } from '@/state/settings';
import { spacing } from '@/theme';

import { usePiSettings } from './use-pi-settings';

export function AlertsSection() {
  const t = useT();
  const online = useLive((x) => x.connection === 'online');
  const s = useSettings(useShallow((x) => ({ sound: x.sound, volume: x.volume, vibration: x.vibration })));
  const set = useSettings((x) => x.set);
  const { state: piState, update: updatePi } = usePiSettings();
  const ready = piState.kind === 'ready' && online;
  const v = piState.kind === 'ready' ? piState.value : null;
  const [sent, setSent] = useState(false);

  const testAlert = () => {
    pi()
      .send('POST', '/test_alert', { pattern: 'repeated' })
      .then(
        () => setSent(true),
        () => {
          haptic(ALERT_PRESENTATION.repeated.haptic, 'repeated');
          speak('voice.test');
        },
      );
    setTimeout(() => setSent(false), 2000);
  };

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
        label={t('settings.sensitivity')}
        disabled={!ready}
        right={
          v ? (
            <Choice<Sensitivity>
              label={t('settings.sensitivity')}
              value={v.sensitivity}
              options={(['low', 'normal', 'high'] as const).map((s) => ({ value: s, label: t(`settings.sens.${s}`) }))}
              onChange={(s) => updatePi({ sensitivity: s })}
              disabled={!ready}
            />
          ) : undefined
        }
      />
      <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.sm }}>
        <Button
          title={sent ? t('settings.testSent') : t('settings.testAlert')}
          icon="notifications"
          variant="secondary"
          disabled={!online}
          onPress={testAlert}
        />
      </View>
    </Section>
  );
}
