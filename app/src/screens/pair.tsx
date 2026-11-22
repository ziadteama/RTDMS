import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRef, useState } from 'react';
import { TextInput, View } from 'react-native';

import SahiNative from '@modules/sahi-native';
import { Button } from '@/components/button';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { getBleLink } from '@/pi/ble';
import type { BleUnit } from '@/pi/ble/types';
import { normalizeBaseUrl, parseQr } from '@/pi/parse';
import { useSecure } from '@/state/secure';
import { DEFAULT_BASE_URL, useSettings } from '@/state/settings';
import { radius, spacing, touch, type, useTheme } from '@/theme';

import { PairBleManual } from './pair-ble-manual';
import { PairFind } from './pair-find';
import { firstTrue, httpReachable, pairOpen, waitBleOnline } from './pair-link';

type Ble = { name: string; token: string };

type Phase = { kind: 'idle' } | { kind: 'busy'; label: string } | { kind: 'error'; label: string } | { kind: 'ok' };

/** QR pairing to the Pi hotspot, or a typed address (mock Pi on a laptop, Pi on a LAN). */
export function Pair({ onDone }: { onDone: () => void }) {
  const t = useT();
  const { colors } = useTheme();
  const [permission, requestPermission] = useCameraPermissions();
  const [address, setAddress] = useState(useSettings.getState().baseUrl);
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const [codeFor, setCodeFor] = useState<string | null>(null);
  const handled = useRef(false);

  /**
   * Pair with the unit. Succeeds when EITHER the Wi-Fi check answers OR the Bluetooth link comes
   * online within 10 s; a Bluetooth-only QR (no Wi-Fi) is judged by Bluetooth alone. On failure the
   * previous Bluetooth pairing is put back.
   */
  const connect = async (baseUrl: string | null, wifi: { ssid: string; password: string } | null, ble: Ble | null) => {
    if (wifi) {
      setPhase({ kind: 'busy', label: t('onb.pair.joining', { ssid: wifi.ssid }) });
      useSecure.getState().setWifi(wifi);
      if (SahiNative) await SahiNative.joinWifi(wifi.ssid, wifi.password).catch(() => false);
    }
    setPhase({ kind: 'busy', label: t('onb.pair.checking') });
    const before = { name: useSettings.getState().bleName, token: useSecure.getState().piToken };
    // Subscribe first: saving the pairing makes the background service start the link at once.
    const wait = ble ? waitBleOnline(getBleLink()) : null;
    if (ble) {
      useSecure.getState().setPiToken(ble.token);
      useSettings.getState().set({ bleName: ble.name, demo: false });
    }
    const checks = [wait?.done, baseUrl && (wifi || !ble) ? httpReachable(baseUrl) : undefined].filter((c): c is Promise<boolean> => !!c);
    const ok = await firstTrue(checks);
    wait?.cancel();
    if (ok) {
      useSettings.getState().set({ ...(baseUrl ? { baseUrl } : {}), demo: false });
      setPhase({ kind: 'ok' });
      onDone();
    } else {
      if (ble) {
        useSecure.getState().setPiToken(before.token);
        useSettings.getState().set({ bleName: before.name });
      }
      setPhase({ kind: 'error', label: ble && !baseUrl ? t('onb.pair.btFail') : t('onb.pair.fail', { url: baseUrl ?? '' }) });
      handled.current = false;
    }
  };

  /** Tap on a unit found by the scan: connect with no code (DEV open mode); fall back to a code if the unit wants one. */
  const onPickUnit = async (unit: BleUnit) => {
    setCodeFor(null);
    setPhase({ kind: 'busy', label: t('onb.pair.checking') });
    const result = await pairOpen(unit);
    if (result === 'ok') {
      setPhase({ kind: 'ok' });
      onDone();
    } else {
      setCodeFor(result === 'needs-code' ? unit.name : null);
      setPhase({ kind: 'error', label: result === 'needs-code' ? t('onb.pair.needsCode') : t('onb.pair.btFail') });
    }
  };

  const onScan = (data: string) => {
    if (handled.current) return;
    const info = parseQr(data, DEFAULT_BASE_URL);
    if (!info) {
      setPhase({ kind: 'error', label: t('onb.pair.badQr') });
      return;
    }
    handled.current = true;
    const ble = info.bleName && info.token ? { name: info.bleName, token: info.token } : null;
    const wifi = info.ssid ? { ssid: info.ssid, password: info.password ?? '' } : null;
    if (wifi) setAddress(info.baseUrl);
    void connect(wifi || !ble ? info.baseUrl : null, wifi, ble);
  };

  const onManual = () => {
    const url = normalizeBaseUrl(address);
    if (!url) {
      setPhase({ kind: 'error', label: t('onb.pair.badUrl') });
      return;
    }
    void connect(url, null, null);
  };

  const camera = process.env.EXPO_OS !== 'web' && permission?.granted;
  return (
    <View style={{ gap: spacing.lg }}>
      {camera ? (
        <View style={{ aspectRatio: 1, borderRadius: radius.lg, borderCurve: 'continuous', overflow: 'hidden', backgroundColor: colors.surface }}>
          <CameraView
            style={{ position: 'absolute', top: 0, bottom: 0, start: 0, end: 0 }}
            barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
            onBarcodeScanned={(r) => onScan(r.data)}
          />
        </View>
      ) : null}
      <View style={{ gap: spacing.md }}>
        <PairFind busy={phase.kind === 'busy'} onPick={(u) => void onPickUnit(u)} onError={(label) => setPhase({ kind: 'error', label })} />
        <Text variant="label" tone="secondary">
          {t('onb.pair.manual')}
        </Text>
        <TextInput
          value={address}
          onChangeText={setAddress}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          accessibilityLabel={t('settings.address')}
          style={[type.body, { minHeight: touch.min, paddingHorizontal: spacing.lg, borderRadius: radius.md, backgroundColor: colors.surface, color: colors.text, writingDirection: 'ltr', textAlign: 'left' }]}
        />
        {phase.kind === 'busy' || phase.kind === 'error' ? (
          <Text tone="secondary" accessibilityLiveRegion="polite" selectable>
            {phase.label}
          </Text>
        ) : null}
        <Button title={t('onb.pair.connect')} icon="wifi" size="lg" onPress={onManual} loading={phase.kind === 'busy'} />
        {!camera && process.env.EXPO_OS !== 'web' ? (
          <Button title={t('onb.perm.camera')} icon="camera" variant="secondary" onPress={() => void requestPermission()} />
        ) : null}
        <PairBleManual
          key={codeFor ?? 'closed'}
          initialOpen={codeFor !== null}
          initialName={codeFor ?? ''}
          busy={phase.kind === 'busy'}
          onInvalid={() => setPhase({ kind: 'error', label: t('onb.pair.badBle') })}
          onSubmit={(ble) => void connect(null, null, ble)}
        />
        <Button
          title={t('onb.pair.demo')}
          variant="ghost"
          onPress={() => {
            useSettings.getState().set({ demo: true });
            onDone();
          }}
        />
      </View>
    </View>
  );
}
