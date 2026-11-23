import { router } from 'expo-router';
import { Alert } from 'react-native';

import { Row, Section } from '@/components/list';
import { calibrationState } from '@/pi/calibration-state';
import { useT } from '@/i18n';
import { useLive } from '@/state/live';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';
import { useTheme } from '@/theme';

export function UnitSection() {
  const t = useT();
  const { colors } = useTheme();
  const online = useLive((s) => s.connection === 'online');
  const link = useLive((s) => s.link);
  const btOff = useLive((s) => s.btOff);
  const calibration = useLive((s) => calibrationState(s.status?.drowsiness));

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
        value={online ? t(link === 'ble' ? 'settings.viaBluetooth' : link === 'http' ? 'settings.viaWifi' : 'settings.connected') : btOff ? t('banner.btOff') : t('settings.notConnected')}
        valueColor={online ? colors.alert.none : undefined}
      />
      <Row
        label={t('settings.calibrate')}
        detail={t('settings.calibrateDetail')}
        value={t(`cal.state.${calibration}`)}
        chevron
        disabled={!online}
        onPress={() => router.push('/calibrate')}
      />
      <Row label={t('settings.connectOther')} icon="qr" chevron onPress={() => router.push('/pair')} />
      <Row label={t('settings.forget')} icon="delete" destructive onPress={forget} />
    </Section>
  );
}
