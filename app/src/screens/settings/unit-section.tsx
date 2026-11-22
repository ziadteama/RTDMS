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
  const link = useLive((s) => s.link);
  const eyeCal = useSettings((s) => s.eyeCalibration);

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
        value={online ? t(link === 'ble' ? 'settings.viaBluetooth' : link === 'http' ? 'settings.viaWifi' : 'settings.connected') : t('settings.notConnected')}
        valueColor={online ? colors.alert.none : undefined}
      />
      <Row
        label={t('settings.eyeCalibration')}
        value={eyeCal ? t(`cal.eye.quality.${eyeCal.quality}`) : t('settings.eyeCalNotDone')}
        valueColor={eyeCal?.quality === 'good' ? colors.alert.none : undefined}
        icon="eye"
        chevron
        onPress={() => router.push('/eye-calibration')}
      />
      <Row
        label={t('settings.drivingPosition')}
        detail={t('settings.drivingPositionDetail')}
        chevron
        disabled={!online}
        onPress={() => router.push('/calibrate')}
      />
      <Row label={t('settings.connectOther')} icon="qr" chevron onPress={() => router.push('/pair')} />
      <Row label={t('settings.forget')} icon="delete" destructive onPress={forget} />
    </Section>
  );
}
