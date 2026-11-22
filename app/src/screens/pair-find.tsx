import { useState } from 'react';
import { Pressable, View } from 'react-native';

import { Button } from '@/components/button';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { getBleLink } from '@/pi/ble';
import { requestBlePermissions } from '@/pi/ble/permissions';
import type { BleUnit } from '@/pi/ble/types';
import { UNIT_BLE_NAME } from '@/pi/ble/uuids';
import { radius, spacing, touch, useTheme } from '@/theme';

/**
 * "Find my Sahi unit": scans for units advertising the Sahi name and lists them (name + signal).
 * Tapping one connects with no code (DEV open mode); the parent handles the connect.
 */
export function PairFind({ busy, onPick, onError }: { busy: boolean; onPick: (unit: BleUnit) => void; onError: (label: string) => void }) {
  const t = useT();
  const { colors } = useTheme();
  const [scanning, setScanning] = useState(false);
  const [units, setUnits] = useState<BleUnit[] | null>(null);

  const find = async () => {
    setScanning(true);
    setUnits(null);
    try {
      if (!(await requestBlePermissions())) return onError(t('onb.pair.btDenied'));
      setUnits(await getBleLink().scan(UNIT_BLE_NAME));
    } catch {
      onError(t('onb.pair.btFail'));
    } finally {
      setScanning(false);
    }
  };

  return (
    <View style={{ gap: spacing.md }}>
      <Button title={units ? t('onb.pair.findAgain') : t('onb.pair.find')} icon="bluetooth" size="lg" onPress={() => void find()} loading={scanning} disabled={busy} />
      {units?.length === 0 ? <Text tone="secondary">{t('onb.pair.noneFound')}</Text> : null}
      {units?.map((u) => (
        <Pressable
          key={u.id}
          accessibilityRole="button"
          accessibilityLabel={u.name}
          disabled={busy}
          onPress={() => onPick(u)}
          style={{ minHeight: touch.min, paddingHorizontal: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}
        >
          <Text>{u.name}</Text>
          <Text tone="secondary">{u.rssi === null ? '' : t('onb.pair.signal', { dbm: u.rssi })}</Text>
        </Pressable>
      ))}
    </View>
  );
}
