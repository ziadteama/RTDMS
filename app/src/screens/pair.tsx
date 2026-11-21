import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRef, useState } from 'react';
import { TextInput, View } from 'react-native';

import SahiNative from '@modules/sahi-native';
import { Button } from '@/components/button';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { normalizeBaseUrl, parseQr, parseStatus } from '@/pi/parse';
import { HttpTransport } from '@/pi/transport';
import { useSecure } from '@/state/secure';
import { DEFAULT_BASE_URL, useSettings } from '@/state/settings';
import { radius, spacing, touch, type, useTheme } from '@/theme';

type Phase = { kind: 'idle' } | { kind: 'busy'; label: string } | { kind: 'error'; label: string } | { kind: 'ok' };

async function reachable(baseUrl: string): Promise<boolean> {
  const tr = new HttpTransport(baseUrl);
  for (let i = 0; i < 3; i++) {
    try {
      if (parseStatus(await tr.get('/status', 2500))) return true;
    } catch {
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
  return false;
}

/** QR pairing to the Pi hotspot, or a typed address (mock Pi on a laptop, Pi on a LAN). */
export function Pair({ onDone }: { onDone: () => void }) {
  const t = useT();
  const { colors } = useTheme();
  const [permission, requestPermission] = useCameraPermissions();
  const [address, setAddress] = useState(useSettings.getState().baseUrl);
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const handled = useRef(false);

  const connect = async (baseUrl: string, wifi: { ssid: string; password: string } | null) => {
    if (wifi) {
      setPhase({ kind: 'busy', label: t('onb.pair.joining', { ssid: wifi.ssid }) });
      useSecure.getState().setWifi(wifi);
      if (SahiNative) await SahiNative.joinWifi(wifi.ssid, wifi.password).catch(() => false);
    }
    setPhase({ kind: 'busy', label: t('onb.pair.checking') });
    if (await reachable(baseUrl)) {
      useSettings.getState().set({ baseUrl, demo: false });
      setPhase({ kind: 'ok' });
      onDone();
    } else {
      setPhase({ kind: 'error', label: t('onb.pair.fail', { url: baseUrl }) });
      handled.current = false;
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
    setAddress(info.baseUrl);
    void connect(info.baseUrl, info.ssid ? { ssid: info.ssid, password: info.password ?? '' } : null);
  };

  const onManual = () => {
    const url = normalizeBaseUrl(address);
    if (!url) {
      setPhase({ kind: 'error', label: t('onb.pair.badUrl') });
      return;
    }
    void connect(url, null);
  };

  const camera = process.env.EXPO_OS !== 'web' && permission?.granted;
  return (
    <View style={{ gap: spacing.xl }}>
      <Text tone="secondary">{t('onb.pair.lead')}</Text>
      <View style={{ aspectRatio: 1, borderRadius: radius.lg, borderCurve: 'continuous', overflow: 'hidden', backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.lg }}>
        {camera ? (
          <CameraView
            style={{ position: 'absolute', top: 0, bottom: 0, start: 0, end: 0 }}
            barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
            onBarcodeScanned={(r) => onScan(r.data)}
          />
        ) : (
          <>
            <Text tone="tertiary" align="center">
              {t('onb.pair.noCamera')}
            </Text>
            {process.env.EXPO_OS !== 'web' ? (
              <Button title={t('onb.perm.allow')} icon="camera" variant="secondary" onPress={() => void requestPermission()} />
            ) : null}
          </>
        )}
      </View>
      <View style={{ gap: spacing.md }}>
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
        <Button title={t('onb.pair.connect')} icon="wifi" onPress={onManual} loading={phase.kind === 'busy'} />
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
