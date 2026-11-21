import { useEvent } from 'expo';
import { Directory, File, Paths } from 'expo-file-system';
import { useLocalSearchParams } from 'expo-router';
import { VideoView, useVideoPlayer } from 'expo-video';
import { useEffect, useState } from 'react';
import { Linking, View } from 'react-native';

import { Banner } from '@/components/banner';
import { Button } from '@/components/button';
import { Row, Section } from '@/components/list';
import { Screen } from '@/components/screen';
import { useT, type StringKey } from '@/i18n';
import { parseIncidents } from '@/pi/parse';
import type { IncidentFrame, PiIncident } from '@/pi/types';
import { IncidentTimeline } from '@/screens/incident-timeline';
import { pi } from '@/services/pi';
import { db, useDbQuery } from '@/state/db';
import { useLive } from '@/state/live';
import { useSettings } from '@/state/settings';
import { radius, spacing, useTheme } from '@/theme';
import { formatDateTime } from '@/utils/format';

function Clip({ source, onTime, seekTo }: { source: string | number; onTime: (s: number) => void; seekTo: { s: number } | null }) {
  const player = useVideoPlayer(source, (p) => {
    p.timeUpdateEventInterval = 0.25;
    p.loop = false;
  });
  const { currentTime } = useEvent(player, 'timeUpdate', { currentTime: 0, currentLiveTimestamp: null, currentOffsetFromLive: null, bufferedPosition: 0 });
  useEffect(() => onTime(currentTime), [currentTime, onTime]);
  useEffect(() => {
    if (seekTo !== null) player.seekBy(seekTo.s - player.currentTime);
  }, [seekTo, player]);
  const { colors } = useTheme();
  return (
    <View style={{ aspectRatio: 4 / 3, borderRadius: radius.md, overflow: 'hidden', backgroundColor: colors.surface }}>
      <VideoView player={player} style={{ flex: 1 }} nativeControls contentFit="contain" />
    </View>
  );
}

/** Local incident (crash / SOS logged on this phone) or a clip that only exists on the Pi ("pi:<id>"). */
export default function IncidentScreen() {
  const t = useT();
  const { colors } = useTheme();
  const lang = useSettings((s) => s.language);
  const online = useLive((s) => s.connection === 'online');
  const { id } = useLocalSearchParams<{ id: string }>();
  const local = useDbQuery(() => (id.startsWith('pi:') ? null : db.getIncident(Number(id))));
  const piId = id.startsWith('pi:') ? id.slice(3) : (local?.piId ?? null);

  const [piInfo, setPiInfo] = useState<PiIncident | null>(null);
  const [frames, setFrames] = useState<IncidentFrame[]>([]);
  const [position, setPosition] = useState(0);
  // a new object per tap, so tapping the same spot twice seeks twice
  const [seek, setSeek] = useState<{ s: number } | null>(null);
  const [download, setDownload] = useState<'idle' | 'busy' | 'done' | 'error'>(local?.clipPath ? 'done' : 'idle');

  useEffect(() => {
    if (!piId || !online) return;
    pi()
      .get('/incidents', 3000)
      .then((r) => setPiInfo(parseIncidents(r).find((i) => i.id === piId) ?? null))
      .catch(() => setPiInfo(null));
    pi()
      .frames(piId)
      .then(setFrames)
      .catch(() => setFrames([]));
  }, [piId, online]);

  const tCrash = local?.t ?? piInfo?.t_crash ?? 0;
  const lat = local?.lat ?? piInfo?.lat ?? null;
  const lon = local?.lon ?? piInfo?.lon ?? null;
  const gPeak = local?.gPeak ?? piInfo?.g_peak ?? null;
  const transport = pi();
  const remote = piId ? transport.clip(piId) : null;
  const source: string | number | null = local?.clipPath ?? (remote ? ('uri' in remote ? remote.uri : remote.asset) : null);

  const save = async () => {
    if (!remote || !('uri' in remote) || !local) return;
    setDownload('busy');
    try {
      const dir = new Directory(Paths.document, 'incidents');
      if (!dir.exists) dir.create();
      const file = await File.downloadFileAsync(remote.uri, new File(dir, `${local.id}.mp4`), { idempotent: true });
      db.saveIncident(local.id, { clipPath: file.uri });
      setDownload('done');
    } catch {
      setDownload('error');
    }
  };

  const yesNo = (b: boolean | null | undefined): string => (b === null || b === undefined ? t('incident.na') : b ? t('incident.yes') : t('incident.no'));
  const checks = local?.checks;
  return (
    <Screen>
      <Section>
        <Row label={t('incident.time')} value={tCrash ? formatDateTime(tCrash, lang) : '—'} />
        {gPeak !== null ? <Row label={t('incident.gPeak')} value={`${gPeak.toFixed(1)} g`} valueColor={colors.alert.max} /> : null}
        {local ? <Row label={t('incident.outcome')} value={t(`incident.outcome.${local.outcome}`)} /> : null}
        <Row
          label={t('incident.location')}
          value={lat !== null && lon !== null ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : t('incident.na')}
          chevron={lat !== null}
          onPress={lat !== null && lon !== null ? () => void Linking.openURL(`https://maps.google.com/?q=${lat},${lon}`) : undefined}
        />
      </Section>
      {checks ? (
        <Section title={t('incident.checks')}>
          {(['flipped', 'faceLost', 'headJerk', 'hrSpike'] as const).map((k) => (
            <Row key={k} label={t(`incident.check.${k}` as StringKey)} value={yesNo(checks[k])} />
          ))}
        </Section>
      ) : null}
      <Section title={t('incident.clip')}>
        <View style={{ padding: spacing.md, gap: spacing.lg }}>
          {source !== null ? (
            <Clip source={source} onTime={setPosition} seekTo={seek} />
          ) : (
            <Banner icon="info" title={t('incident.notOnPi')} />
          )}
          {frames.length || local?.motion.length ? (
            <IncidentTimeline
              tCrash={tCrash}
              frames={frames}
              motion={local?.motion ?? []}
              positionS={position}
              onSeek={(s) => setSeek({ s })}
            />
          ) : null}
          {local && remote && 'uri' in remote ? (
            <Button
              title={download === 'done' ? t('incident.downloaded') : download === 'busy' ? t('incident.downloading') : t('incident.download')}
              icon="download"
              variant="secondary"
              loading={download === 'busy'}
              disabled={download === 'done' || !online}
              onPress={() => void save()}
            />
          ) : null}
        </View>
      </Section>
    </Screen>
  );
}
