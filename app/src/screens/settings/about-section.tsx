import Constants from 'expo-constants';
import { router } from 'expo-router';
import { useRef } from 'react';

import { Row, Section } from '@/components/list';
import { useT } from '@/i18n';

export function AboutSection() {
  const t = useT();
  const taps = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handlePress = () => {
    if (timer.current) clearTimeout(timer.current);
    taps.current += 1;
    if (taps.current >= 7) {
      taps.current = 0;
      router.push('/diagnostics');
      return;
    }
    timer.current = setTimeout(() => {
      taps.current = 0;
    }, 2000);
  };

  return (
    <Section title={t('settings.about')}>
      <Row label={t('settings.version')} value={Constants.expoConfig?.version ?? '—'} onPress={handlePress} />
    </Section>
  );
}
