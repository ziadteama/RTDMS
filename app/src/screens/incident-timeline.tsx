import { memo, useState } from 'react';
import { Pressable, View } from 'react-native';

import { Text } from '@/components/text';
import { useT } from '@/i18n';
import type { AlertPattern, IncidentFrame } from '@/pi/types';
import { radius, size, spacing, useTheme } from '@/theme';

const BEFORE_MS = 15_000;
const SPAN_MS = 25_000;

type Segment = { from: number; to: number; value: string };

/** Collapse per-frame values into runs, so 250 frames draw as a handful of views. */
function runs(frames: IncidentFrame[], t0: number, pick: (f: IncidentFrame) => string): Segment[] {
  const out: Segment[] = [];
  for (const f of frames) {
    const x = (f.t - t0) / SPAN_MS;
    const v = pick(f);
    const last = out[out.length - 1];
    if (last && last.value === v) last.to = x;
    else out.push({ from: x, to: x, value: v });
  }
  for (let i = 0; i < out.length - 1; i++) out[i]!.to = out[i + 1]!.from;
  if (out.length) out[out.length - 1]!.to = Math.max(out[out.length - 1]!.to, out[out.length - 1]!.from + 0.004);
  return out;
}

/**
 * Sensor timeline under the clip: fusion alert, face present (Pi ring buffer data.jsonl) and the
 * phone's |a| around the impact. 0 s = the crash; the playhead follows the video, tap to seek.
 */
export const IncidentTimeline = memo(function IncidentTimeline({
  tCrash,
  frames,
  motion,
  positionS,
  onSeek,
}: {
  tCrash: number;
  frames: IncidentFrame[];
  motion: [number, number][];
  positionS: number;
  onSeek: (s: number) => void;
}) {
  const t = useT();
  const { colors } = useTheme();
  const t0 = tCrash - BEFORE_MS;
  const alert = runs(frames, t0, (f) => f.alert?.pattern ?? 'unknown');
  const face = runs(frames, t0, (f) => (f.status.face ? 'yes' : 'no'));
  const gMax = Math.max(4, ...motion.map((m) => m[1]));
  const [width, setWidth] = useState(0);

  const Track = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <View style={{ gap: spacing.xs }}>
      <Text variant="caption" tone="secondary">
        {label}
      </Text>
      <View style={{ height: size.track, borderRadius: radius.sm / 2, overflow: 'hidden', backgroundColor: colors.surfaceRaised }}>{children}</View>
    </View>
  );

  const seg = (s: Segment, color: string) => (
    <View key={`${s.from}`} style={{ position: 'absolute', top: 0, bottom: 0, start: `${s.from * 100}%`, width: `${Math.max(0.4, (s.to - s.from) * 100)}%`, backgroundColor: color }} />
  );

  return (
    <View style={{ gap: spacing.md }}>
      <Pressable
        accessibilityRole="adjustable"
        accessibilityLabel={t('incident.timeline')}
        onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
        onPress={(e) => {
          if (width) onSeek(Math.max(0, Math.min(1, e.nativeEvent.locationX / width)) * (SPAN_MS / 1000));
        }}
        style={{ gap: spacing.md }}
      >
        <Track label={t('incident.alertTrack')}>
          {alert.map((s) => seg(s, s.value === 'unknown' ? colors.unknown : colors.alert[s.value as AlertPattern]))}
        </Track>
        <Track label={t('incident.faceTrack')}>{face.map((s) => seg(s, s.value === 'yes' ? colors.textTertiary : colors.alert.continuous))}</Track>
        <Track label={t('incident.gTrack')}>
          {motion.map(([tm, g], i) => (
            <View
              key={i}
              style={{
                position: 'absolute',
                bottom: 0,
                start: `${((tm - t0) / SPAN_MS) * 100}%`,
                width: size.line,
                height: `${Math.min(100, (g / gMax) * 100)}%`,
                backgroundColor: g >= 4 ? colors.alert.max : colors.textSecondary,
              }}
            />
          ))}
        </Track>
        <View
          pointerEvents="none"
          style={{ position: 'absolute', top: 0, bottom: 0, start: `${Math.min(100, (positionS / (SPAN_MS / 1000)) * 100)}%`, width: size.line, backgroundColor: colors.text }}
        />
      </Pressable>
      <View style={{ height: size.trackLabel }}>
        <Text variant="caption" tone="tertiary" style={{ position: 'absolute', start: 0 }}>
          −15 s
        </Text>
        {/* 0 s = the crash, 15 s into the 25 s clip */}
        <Text variant="caption" tone="secondary" style={{ position: 'absolute', start: `${(BEFORE_MS / SPAN_MS) * 100}%` }}>
          0
        </Text>
        <Text variant="caption" tone="tertiary" style={{ position: 'absolute', end: 0 }}>
          +10 s
        </Text>
      </View>
    </View>
  );
});
