import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert } from 'react-native';

import { Banner } from '@/components/banner';
import { Row, Section } from '@/components/list';
import { dx, type DiagnosticsKey } from '@/i18n/diagnostics';
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

export function UnitHealth() {
  const { colors } = useTheme();
  const online = useLive((s) => s.connection === 'online');
  const fps = useLive((s) => s.status?.fps ?? null);
  const temp = useLive((s) => s.status?.temp_c ?? null);
  const state = useHealth();
  const [sent, setSent] = useState<string | null>(null);

  const control = (path: '/system/restart' | '/system/shutdown', confirm: DiagnosticsKey, title: DiagnosticsKey) =>
    Alert.alert(dx(title), dx(confirm), [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Confirm',
        style: 'destructive',
        onPress: () => void pi().send('POST', path).then(() => setSent(path), () => setSent(null)),
      },
    ]);

  if (!online) {
    return <Banner icon="wifiOff" tone="danger" title={dx('diag.health.offline')} detail={dx('diag.health.offlineHint')} />;
  }

  const h = state.kind === 'ready' ? state.h : null;
  const th = h ? decodeThrottled(h.throttled) : null;
  const flags: string[] = [];
  if (th) {
    const add = (now: boolean, ever: boolean, key: DiagnosticsKey) => {
      if (now) flags.push(`${dx(key)} (${dx('diag.health.now')})`);
      else if (ever) flags.push(`${dx(key)} (${dx('diag.health.sinceBoot')})`);
    };
    add(th.underVoltageNow, th.underVoltageOccurred, 'diag.health.underVoltage');
    add(th.throttledNow, th.throttledOccurred, 'diag.health.throttled');
    add(th.freqCappedNow, th.freqCappedOccurred, 'diag.health.freqCapped');
    add(th.softTempLimitNow, th.softTempLimitOccurred, 'diag.health.softTemp');
  }
  const throttleNow = th && (th.underVoltageNow || th.throttledNow || th.freqCappedNow);

  return (
    <>
      {state.kind === 'unsupported' ? <Banner icon="info" tone="warning" title={dx('diag.health.unavailable')} /> : null}
      <Section title={dx('diag.health.system')}>
        <Row label={dx('diag.health.cpu')} value={h ? `${Math.round(h.cpu_pct)} %` : '—'} />
        <Row label={dx('diag.health.temp')} value={(h?.temp_c ?? temp) !== null ? `${(h?.temp_c ?? temp)!.toFixed(1)} °C` : '—'} />
        <Row
          label={dx('diag.health.throttling')}
          value={th ? (flags.length ? flags.join(', ') : dx('diag.health.throttleNone')) : '—'}
          valueColor={throttleNow ? colors.alert.continuous : flags.length ? colors.alert.short_beep : undefined}
        />
        <Row label={dx('diag.health.volts')} value={h?.volts_5v != null ? `${h.volts_5v.toFixed(2)} V` : '—'} />
        <Row label={dx('diag.health.fps')} value={(h?.fps ?? fps) !== null ? `${(h?.fps ?? fps)!.toFixed(1)} fps` : '—'} />
        <Row label={dx('diag.health.camera')} value={h ? dx(h.camera === 'ok' ? 'diag.health.ok' : 'diag.health.lost') : '—'} valueColor={h?.camera === 'lost' ? colors.alert.continuous : undefined} />
        <Row label={dx('diag.health.memory')} value={h ? `${gb(h.mem_used_mb)} / ${gb(h.mem_total_mb)}` : '—'} />
        <Row label={dx('diag.health.storage')} value={h ? `${gb(h.disk_free_mb)} / ${gb(h.disk_total_mb)}` : '—'} />
        <Row label={dx('diag.health.uptime')} value={h ? uptime(h.uptime_s) : '—'} />
      </Section>
      {h ? (
        <Section title={dx('diag.health.models')}>
          {Object.entries(h.models).map(([name, s]) => (
            <Row
              key={name}
              label={name}
              value={dx(s === 'running' ? 'diag.health.running' : s === 'off' ? 'diag.health.off' : 'diag.health.error')}
              valueColor={s === 'error' ? colors.alert.continuous : s === 'running' ? colors.alert.none : undefined}
            />
          ))}
        </Section>
      ) : null}
      <Section title={dx('diag.health.controls')}>
        <Row
          label={dx('diag.health.restart')}
          icon="restart"
          value={sent === '/system/restart' ? dx('diag.health.sent') : undefined}
          onPress={() => control('/system/restart', 'diag.health.restartConfirm', 'diag.health.restart')}
        />
        <Row
          label={dx('diag.health.shutdown')}
          icon="power"
          destructive
          value={sent === '/system/shutdown' ? dx('diag.health.sent') : undefined}
          onPress={() => control('/system/shutdown', 'diag.health.shutdownConfirm', 'diag.health.shutdown')}
        />
      </Section>
    </>
  );
}
