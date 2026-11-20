import { router, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';

import { Sparkline } from '@/components/bar-chart';
import { Dot } from '@/components/dot';
import { Row, Section } from '@/components/list';
import { Metric } from '@/components/metric';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useT, type StringKey } from '@/i18n';
import type { AlertPattern } from '@/pi/types';
import { scoreColor } from '@/screens/score-color';
import { db, useDbQuery } from '@/state/db';
import { useSettings } from '@/state/settings';
import { radius, spacing, useTheme } from '@/theme';
import { formatDateTime, formatDuration, formatTime } from '@/utils/format';
import { useNow } from '@/hooks/use-now';

const PATTERNS: Exclude<AlertPattern, 'none'>[] = ['short_beep', 'repeated', 'continuous', 'max'];

export default function TripDetail() {
  const t = useT();
  const { colors } = useTheme();
  const lang = useSettings((s) => s.language);
  const { id } = useLocalSearchParams<{ id: string }>();
  const now = useNow();
  const tripId = Number(id);
  const trip = useDbQuery(() => db.getTrip(tripId));
  const events = useDbQuery(() => db.events(tripId));
  const hr = useDbQuery(() => db.hr(tripId));
  const incidents = useDbQuery(() => db.incidents(tripId));
  if (!trip) return null;
  const units = { h: t('common.h'), min: t('common.min'), s: t('live.s') };
  const s = trip.summary;
  const label = (e: (typeof events)[number]): string => {
    switch (e.kind) {
      case 'alert':
        return t(`pattern.${e.value as AlertPattern}`);
      case 'state':
        return t(`state.${e.value}` as StringKey);
      case 'crash':
        return t('event.crash', { g: e.detail ?? '—' });
      case 'sos':
        return t('event.sos');
      case 'connected':
        return t('event.connected');
      case 'disconnected':
        return t('event.disconnected');
    }
  };
  const dot = (e: (typeof events)[number]) =>
    e.kind === 'alert' ? colors.alert[e.value as AlertPattern] : e.kind === 'crash' || e.kind === 'sos' ? colors.alert.max : colors.textTertiary;
  return (
    <Screen>
      <Text variant="headline">{formatDateTime(trip.startedAt, lang)}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xl, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.lg }}>
        <Metric label={t('trip.score')} value={trip.score} color={scoreColor(trip.score, colors)} />
        <Metric label={t('trip.duration')} value={formatDuration((trip.endedAt ?? now) - trip.startedAt, units)} />
        <Metric label={t('trip.longestClosure')} value={(s.longestClosureMs / 1000).toFixed(1)} unit={t('live.s')} />
        <Metric label={t('trip.phoneTime')} value={formatDuration(s.phoneMs, units)} />
      </View>
      <Section title={t('trip.alertsByType')}>
        {PATTERNS.map((p) => (
          <Row key={p} label={t(`pattern.${p}`)} value={String(s.alerts[p])} right={<Dot large color={colors.alert[p]} />} />
        ))}
      </Section>
      <Section title={t('trip.hrTrend')}>
        <View style={{ padding: spacing.lg, gap: spacing.sm }}>
          {hr.length >= 2 ? (
            <>
              <Sparkline points={hr.map((h) => h.bpm)} />
              <Text variant="caption" tone="secondary">
                {Math.round(Math.min(...hr.map((h) => h.bpm)))}–{Math.round(Math.max(...hr.map((h) => h.bpm)))} {t('live.bpm')}
              </Text>
            </>
          ) : (
            <Text tone="tertiary">{t('trip.noHr')}</Text>
          )}
        </View>
      </Section>
      {incidents.length ? (
        <Section title={t('trip.incidents')}>
          {incidents.map((i) => (
            <Row
              key={i.id}
              icon={i.kind === 'crash' ? 'crash' : 'sos'}
              iconColor={colors.alert.continuous}
              label={i.kind === 'crash' ? t('event.crash', { g: i.gPeak ?? '—' }) : t('event.sos')}
              detail={t(`incident.outcome.${i.outcome}`)}
              chevron
              onPress={() => router.push({ pathname: '/incident/[id]', params: { id: String(i.id) } })}
            />
          ))}
        </Section>
      ) : null}
      <Section title={t('trip.timeline')}>
        {events.length === 0 ? <Row label={t('trip.noEvents')} /> : null}
        {events.slice(-200).map((e) => (
          <Row
            key={e.id}
            label={label(e)}
            detail={e.kind === 'alert' && e.detail ? e.detail : undefined}
            value={formatTime(e.t, lang)}
            right={<Dot color={dot(e)} />}
          />
        ))}
      </Section>
      <Section>
        <Row
          label={t('trip.delete')}
          icon="delete"
          destructive
          onPress={() => {
            db.deleteTrip(trip.id);
            router.back();
          }}
        />
      </Section>
    </Screen>
  );
}
