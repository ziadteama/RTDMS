import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, Pressable, StyleSheet, View } from 'react-native';

import { BarChart } from '@/components/bar-chart';
import { Row, Section } from '@/components/list';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { parseIncidents } from '@/pi/parse';
import type { PiIncident } from '@/pi/types';
import { pi } from '@/services/pi';
import { db, useDbQuery } from '@/state/db';
import { useLive } from '@/state/live';
import { radius, spacing, touch, useTheme } from '@/theme';
import type { Trip } from '@/trips/model';
import { weeklyTrend } from '@/trips/score';
import { formatDateTime, formatDuration, formatWeek } from '@/utils/format';
import { useNow } from '@/hooks/use-now';

import { scoreColor } from '../score-color';

function alertCount(trip: Trip): number {
  const a = trip.summary.alerts;
  return a.short_beep + a.repeated + a.continuous + a.max;
}

function TripRow({ trip, first, last }: { trip: Trip; first: boolean; last: boolean }) {
  const t = useT();
  const { colors } = useTheme();
  const units = { h: t('common.h'), min: t('common.min'), s: t('live.s') };
  return (
    <Pressable
      onPress={() => router.push({ pathname: '/trip/[id]', params: { id: String(trip.id) } })}
      accessibilityRole="button"
      style={({ pressed }) => ({
        backgroundColor: pressed ? colors.surfaceRaised : colors.surface,
        borderTopStartRadius: first ? radius.md : 0,
        borderTopEndRadius: first ? radius.md : 0,
        borderBottomStartRadius: last ? radius.md : 0,
        borderBottomEndRadius: last ? radius.md : 0,
        minHeight: touch.large,
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.md,
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.lg,
      })}
    >
      <View style={{ flex: 1, gap: spacing.xxs }}>
        <Text variant="body">{formatDateTime(trip.startedAt)}</Text>
        <Text variant="caption" tone="secondary">
          {trip.endedAt === null ? t('trips.inProgress') : formatDuration(trip.endedAt - trip.startedAt, units)} · {(alertCount(trip) === 1 ? t('trips.alertsOne') : t('trips.alerts', { n: alertCount(trip) }))}
          {trip.demo ? ` · ${t('trips.demo')}` : ''}
        </Text>
      </View>
      <Text variant="metricSmall" color={scoreColor(trip.score, colors)} accessibilityLabel={`${t('trips.score')} ${trip.score ?? '—'}`}>
        {trip.score ?? '—'}
      </Text>
    </Pressable>
  );
}

function Header({ trips }: { trips: Trip[] }) {
  const t = useT();
  const { colors } = useTheme();
  const online = useLive((s) => s.connection === 'online');
  const incidents = useDbQuery(() => db.incidents());
  const [piClips, setPiClips] = useState<PiIncident[] | null>(null);
  useFocusEffect(
    useCallback(() => {
      if (!online) return;
      pi()
        .get('/incidents', 3000)
        .then((v) => setPiClips(parseIncidents(v)))
        .catch(() => setPiClips(null));
    }, [online]),
  );
  const now = useNow(60_000);
  const trend = weeklyTrend(trips, now);
  const linked = new Set(incidents.map((i) => i.piId));
  const piOnly = (piClips ?? []).filter((c) => !linked.has(c.id));
  return (
    <View style={{ gap: spacing.lg, paddingBottom: spacing.lg }}>
      <Section title={t('trips.weekly')}>
        <View style={{ padding: spacing.lg }}>
          <BarChart
            label={t('trips.weekly')}
            max={100}
            data={trend.map((w) => ({ key: String(w.week), value: w.score, label: formatWeek(w.week), color: w.score === null ? undefined : scoreColor(w.score, colors) }))}
          />
        </View>
      </Section>
      {incidents.length ? (
        <Section title={t('trip.incidents')}>
          {incidents.slice(0, 5).map((i) => (
            <Row
              key={i.id}
              icon={i.kind === 'crash' ? 'crash' : 'sos'}
              iconColor={colors.alert.continuous}
              label={i.kind === 'crash' ? t('event.crash', { g: i.gPeak ?? '—' }) : t('event.sos')}
              detail={`${formatDateTime(i.t)} · ${t(`incident.outcome.${i.outcome}`)}`}
              chevron
              onPress={() => router.push({ pathname: '/incident/[id]', params: { id: String(i.id) } })}
            />
          ))}
        </Section>
      ) : null}
      {piOnly.length ? (
        <Section title={t('incident.piList')}>
          {piOnly.map((c) => (
            <Row
              key={c.id}
              icon="play"
              label={formatDateTime(c.t_crash)}
              detail={`${c.g_peak.toFixed(1)} g · ${c.duration_s} s`}
              chevron
              onPress={() => router.push({ pathname: '/incident/[id]', params: { id: `pi:${c.id}` } })}
            />
          ))}
        </Section>
      ) : null}
    </View>
  );
}

export function Trips() {
  const t = useT();
  const { colors } = useTheme();
  const trips = useDbQuery(() => db.listTrips());
  return (
    <FlatList
      contentInsetAdjustmentBehavior="automatic"
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxxl }}
      data={trips}
      keyExtractor={(trip) => String(trip.id)}
      ListHeaderComponent={<Header trips={trips} />}
      ItemSeparatorComponent={() => <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.separator, marginStart: spacing.lg }} />}
      renderItem={({ item, index }) => <TripRow trip={item} first={index === 0} last={index === trips.length - 1} />}
      ListEmptyComponent={
        <Text tone="secondary" align="center">
          {t('trips.empty')}
        </Text>
      }
    />
  );
}
