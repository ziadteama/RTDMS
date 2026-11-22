import { router } from 'expo-router';
import { useEffect, useState } from 'react';

import { Button } from '@/components/button';
import { Row, Section } from '@/components/list';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import type { IconName } from '@/components/icon';
import { useT, type StringKey } from '@/i18n';
import { permission, type PermissionKey, type PermissionState } from '@/services/permissions';
import { useTheme } from '@/theme';

const ITEMS: { key: PermissionKey; icon: IconName; label: StringKey; why: StringKey }[] = [
  { key: 'location', icon: 'location', label: 'onb.perm.location', why: 'onb.perm.locationWhy' },
  { key: 'notifications', icon: 'notifications', label: 'onb.perm.notifications', why: 'onb.perm.notificationsWhy' },
  { key: 'sms', icon: 'sms', label: 'onb.perm.sms', why: 'onb.perm.smsWhy' },
  { key: 'bluetooth', icon: 'bluetooth', label: 'onb.perm.bluetooth', why: 'onb.perm.bluetoothWhy' },
  { key: 'camera', icon: 'camera', label: 'onb.perm.camera', why: 'onb.perm.cameraWhy' },
];

export default function Permissions() {
  const t = useT();
  const { colors } = useTheme();
  const [state, setState] = useState<Partial<Record<PermissionKey, PermissionState>>>({});

  useEffect(() => {
    void Promise.all(ITEMS.map(async (i) => [i.key, await permission(i.key, false)] as const)).then((r) => setState(Object.fromEntries(r)));
  }, []);

  const ask = async (key: PermissionKey) => {
    const result = await permission(key, true);
    setState((prev) => ({ ...prev, [key]: result }));
  };

  return (
    <Screen>
      <Section>
        {ITEMS.map((i) => {
          const s = state[i.key];
          return (
            <Row
              key={i.key}
              icon={i.icon}
              label={t(i.label)}
              detail={t(i.why)}
              right={
                s === 'granted' ? (
                  <Text variant="label" color={colors.alert.none}>
                    {t('onb.perm.granted')}
                  </Text>
                ) : s === 'unsupported' ? (
                  <Text variant="caption" tone="tertiary">
                    {t('onb.perm.unsupported')}
                  </Text>
                ) : (
                  <Button
                    title={s === 'denied' ? t('onb.perm.denied') : t('onb.perm.allow')}
                    variant="secondary"
                    onPress={() => void ask(i.key)}
                  />
                )
              }
            />
          );
        })}
      </Section>
      <Button title={t('onb.continue')} size="lg" onPress={() => router.push('/connect')} />
    </Screen>
  );
}
