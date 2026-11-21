import { reloadAppAsync } from 'expo';
import { router } from 'expo-router';
import { Alert } from 'react-native';

import { Toggle } from '@/components/controls';
import { Row, Section } from '@/components/list';
import { useT } from '@/i18n';
import { relay } from '@/services/relay/client';
import { db } from '@/state/db';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';
import { clearKv } from '@/state/storage';

export function PrivacySection() {
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
          void relay.unregister().catch(() => {});
          db.wipe();
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
