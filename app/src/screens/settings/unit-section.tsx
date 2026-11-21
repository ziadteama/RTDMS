import { router } from 'expo-router';
import { Alert } from 'react-native';

import { Row, Section } from '@/components/list';
import { useT } from '@/i18n';
import { useLive } from '@/state/live';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';
import { useTheme } from '@/theme';

export function UnitSection() {
  const t = useT();
  const { colors } = useTheme();
  const online = useLive((s) => s.connection === 'online');

  const forget = () => {
    Alert.alert(t('settings.forget'), t('settings.forgetConfirm'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('common.delete'),
        style: 'destructive',
        onPress: () => {
          useSecure.getState().setWifi(null);
          useSettings.getState().set({ baseUrl: '' });
        },
      },
    ]);
  };

  return (
    <Section title={t('settings.unit')}>
      <Row
        label={t('settings.status')}
        value={online ? t('settings.connected') : t('settings.notConnected')}
        valueColor={online ? colors.alert.none : undefined}
      />
      <Row
        label={t('settings.calibrate')}
        icon="eye"
        chevron
        disabled={!online}
        onPress={() => router.push('/calibrate')}
      />
      <Row label={t('settings.forget')} icon="delete" destructive onPress={forget} />
    </Section>
  );
}
