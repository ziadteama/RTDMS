import { router } from 'expo-router';

import { Row, Section } from '@/components/list';
import { useT } from '@/i18n';
import { db, useDbQuery } from '@/state/db';
import { useTheme } from '@/theme';
import { formatDateTime } from '@/utils/format';

import { scoreColor } from '../score-color';

/** Idle Drive screen: the most recent finished trip, so the screen is never an empty void. */
export function LastTrip() {
  const t = useT();
  const { colors } = useTheme();
  const trip = useDbQuery(() => db.listTrips().find((x) => x.endedAt !== null) ?? null);
  if (!trip) return null;
  return (
    <Section title={t('live.lastTrip')}>
      <Row
        label={formatDateTime(trip.startedAt)}
        value={trip.score === null ? '—' : String(trip.score)}
        valueColor={trip.score === null ? undefined : scoreColor(trip.score, colors)}
        chevron
        onPress={() => router.push({ pathname: '/trip/[id]', params: { id: String(trip.id) } })}
      />
    </Section>
  );
}
