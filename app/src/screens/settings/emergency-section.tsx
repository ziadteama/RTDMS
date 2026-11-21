import { router } from 'expo-router';
import { useShallow } from 'zustand/react/shallow';

import { Choice, Toggle } from '@/components/controls';
import { Row, Section } from '@/components/list';
import { useT } from '@/i18n';
import { useSecure } from '@/state/secure';
import { useSettings, type CallTarget } from '@/state/settings';

import { EmergencyNumber } from './emergency-number';

export function EmergencySection() {
  const t = useT();
  const s = useSettings(useShallow((x) => ({ crash: x.crashDetection, callTarget: x.callTarget, ambulance: x.emergencyNumber })));
  const set = useSettings((x) => x.set);
  const contacts = useSecure((x) => x.contacts.length);

  return (
    <Section title={t('settings.emergency')} footer={t('settings.crashFooter')}>
      <Row label={t('settings.contacts')} icon="person" value={String(contacts)} chevron onPress={() => router.push('/contacts')} />
      <Row
        label={t('settings.callTarget')}
        icon="call"
        right={
          <Choice<CallTarget>
            label={t('settings.callTarget')}
            value={s.callTarget}
            options={[
              { value: 'ambulance', label: t('settings.call.ambulance', { n: s.ambulance }) },
              { value: 'contact', label: t('settings.call.contact') },
            ]}
            onChange={(v) => set({ callTarget: v })}
          />
        }
      />
      <EmergencyNumber />
      <Row label={t('settings.crash')} icon="crash" right={<Toggle label={t('settings.crash')} value={s.crash} onChange={(v) => set({ crashDetection: v })} />} />
    </Section>
  );
}
