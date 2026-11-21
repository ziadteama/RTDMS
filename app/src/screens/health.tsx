import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert } from 'react-native';

import { Banner } from '@/components/banner';
import { Row, Section } from '@/components/list';
import { Screen } from '@/components/screen';
import { useT, type StringKey } from '@/i18n';
import { decodeThrottled, parseHealth } from '@/pi/parse';
import { isNotSupported } from '@/pi/transport';
import type { PiHealth } from '@/pi/types';
import { pi } from '@/services/pi';
import { useLive } from '@/state/live';
import { useTheme } from '@/theme';

type State = { kind: 'loading' } | { kind: 'unsupported' } | { kind: 'ready'; h: PiHealth };

function uptime(s: number): string {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d ? `${d}d ${h}h` : `${h}h ${m}m`;
}

const gb = (mb: number) => `${(mb / 1024).toFixed(1)} GB`;

/** Polls GET /health once a second while this tab is visible, never in the background. */
function useHealth(): State {
  const [state, setState] = useState<State>({ kind: 'loading' });
  useFocusEffect(
    useCallback(() => {
      let alive = true;
      const tick = () =>
        pi()
          .get('/health', 1500)
          .then((v) => {
            const h = parseHealth(v);
            if (alive && h) setState({ kind: 'ready', h });
          })
          .catch((e: unknown) => {
            if (alive && isNotSupported(e)) setState({ kind: 'unsupported' });
          });
      void tick();
      const id = setInterval(tick, 1000);
      return () => {
        alive = false;
        clearInterval(id);
      };
    }, []),
  );
  return state;
}

export function Health() {
  const t = useT();
  const { colors } = useTheme();
  const online = useLive((s) => s.connection === 'online');
  // /status carries fps and temperature even on a Pi without /health.
  const fps = useLive((s) => s.status?.fps ?? null);
  const temp = useLive((s) => s.status?.temp_c ?? null);
  const state = useHealth();
  const [sent, setSent] = useState<string | null>(null);

  const control = (path: '/system/restart' | '/system/shutdown', confirm: StringKey, title: StringKey) =>
    Alert.alert(t(title), t(confirm), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('common.confirm'),
        style: 'destructive',
        onPress: () => void pi().send('POST', path).then(() => setSent(path), () => setSent(null)),
      },
    ]);

  if (!online)
    return (
      <Screen>
        <Banner icon="wifiOff" tone="danger" title={t('banner.offline')} detail={t('banner.offlineHint')} />
      </Screen>
    );

  const h = state.kind === 'ready' ? state.h : null;
  const th = h ? decodeThrottled(h.throttled) : null;
  const flags: string[] = [];
  if (th) {
    const add = (now: boolean, ever: boolean, key: StringKey) => {
      if (now) flags.push(`${t(key)} (${t('health.now')})`);
      else if (ever) flags.push(`${t(key)} (${t('health.sinceBoot')})`);
    };
    add(th.underVoltageNow, th.underVoltageOccurred, 'health.underVoltage');
    add(th.throttledNow, th.throttledOccurred, 'health.throttled');
    add(th.freqCappedNow, th.freqCappedOccurred, 'health.freqCapped');
    add(th.softTempLimitNow, th.softTempLimitOccurred, 'health.softTemp');
  }
  const throttleNow = th && (th.underVoltageNow || th.throttledNow || th.freqCappedNow);
  return (
    <Screen>
      {state.kind === 'unsupported' ? <Banner icon="info" tone="warning" title={t('health.unavailable')} /> : null}
      <Section title={t('health.system')}>
        <Row label={t('health.cpu')} value={h ? `${Math.round(h.cpu_pct)} %` : '—'} />
        <Row label={t('health.temp')} value={(h?.temp_c ?? temp) !== null ? `${(h?.temp_c ?? temp)!.toFixed(1)} °C` : '—'} />
        <Row
          label={t('health.throttling')}
          value={th ? (flags.length ? flags.join(', ') : t('health.throttleNone')) : '—'}
          valueColor={throttleNow ? colors.alert.continuous : flags.length ? colors.alert.short_beep : undefined}
        />
        <Row label={t('health.volts')} value={h?.volts_5v != null ? `${h.volts_5v.toFixed(2)} V` : '—'} />
        <Row label={t('health.fps')} value={(h?.fps ?? fps) !== null ? `${(h?.fps ?? fps)!.toFixed(1)} fps` : '—'} />
        <Row label={t('health.camera')} value={h ? t(h.camera === 'ok' ? 'health.ok' : 'health.lost') : '—'} valueColor={h?.camera === 'lost' ? colors.alert.continuous : undefined} />
        <Row label={t('health.memory')} value={h ? `${gb(h.mem_used_mb)} / ${gb(h.mem_total_mb)}` : '—'} />
        <Row label={t('health.storage')} value={h ? `${gb(h.disk_free_mb)} / ${gb(h.disk_total_mb)}` : '—'} />
        <Row label={t('health.uptime')} value={h ? uptime(h.uptime_s) : '—'} />
      </Section>
      {h ? (
        <Section title={t('health.models')}>
          {Object.entries(h.models).map(([name, s]) => (
            <Row
              key={name}
              label={name}
              value={t(s === 'running' ? 'health.running' : s === 'off' ? 'health.off' : 'health.error')}
              valueColor={s === 'error' ? colors.alert.continuous : s === 'running' ? colors.alert.none : undefined}
            />
          ))}
        </Section>
      ) : null}
      <Section title={t('health.controls')}>
        <Row
          label={t('health.restart')}
          icon="restart"
          value={sent === '/system/restart' ? t('health.sent') : undefined}
          onPress={() => control('/system/restart', 'health.restartConfirm', 'health.restart')}
        />
        <Row
          label={t('health.shutdown')}
          icon="power"
          destructive
          value={sent === '/system/shutdown' ? t('health.sent') : undefined}
          onPress={() => control('/system/shutdown', 'health.shutdownConfirm', 'health.shutdown')}
        />
      </Section>
    </Screen>
  );
}
