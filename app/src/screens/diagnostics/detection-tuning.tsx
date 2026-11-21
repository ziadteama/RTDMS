import { View } from 'react-native';

import { Choice, SliderControl, Toggle } from '@/components/controls';
import { Row, Section } from '@/components/list';
import { Text } from '@/components/text';
import { dx } from '@/i18n/diagnostics';
import type { PiSettings, Sensitivity } from '@/pi/types';
import { usePiSettings } from '@/screens/settings/use-pi-settings';
import { useLive } from '@/state/live';
import { spacing } from '@/theme';

function SliderRow({
  label,
  value,
  unit,
  min,
  max,
  step,
  onChange,
  disabled,
}: {
  label: string;
  value: number;
  unit: string;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm, opacity: disabled ? 0.45 : 1 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <Text>{label}</Text>
        <Text tone="secondary" style={{ fontVariant: ['tabular-nums'] }}>
          {value.toFixed(1)} {unit}
        </Text>
      </View>
      <SliderControl value={value} min={min} max={max} step={step} onChange={onChange} disabled={disabled} />
    </View>
  );
}

export function DetectionTuning() {
  const online = useLive((s) => s.connection === 'online');
  const { state, update } = usePiSettings();
  const ready = state.kind === 'ready' && online;
  const v: PiSettings | null = state.kind === 'ready' ? state.value : null;
  const footer = !online ? dx('diag.det.offlineFooter') : state.kind === 'unsupported' ? dx('diag.det.unsupported') : dx('diag.det.footer');

  return (
    <Section title={dx('diag.section.detection')} footer={footer}>
      <Row
        label={dx('diag.det.profile')}
        disabled={!ready}
        right={
          v ? (
            <Choice
              label={dx('diag.det.profile')}
              value={v.profile}
              options={v.profiles.map((p) => ({ value: p, label: p }))}
              onChange={(p) => update({ profile: p })}
              disabled={!ready}
            />
          ) : undefined
        }
      />
      <Row
        label={dx('diag.det.sensitivity')}
        disabled={!ready}
        right={
          v ? (
            <Choice<Sensitivity>
              label={dx('diag.det.sensitivity')}
              value={v.sensitivity}
              options={(['low', 'normal', 'high'] as const).map((s) => ({ value: s, label: dx(`diag.det.sens.${s}`) }))}
              onChange={(s) => update({ sensitivity: s })}
              disabled={!ready}
            />
          ) : undefined
        }
      />
      <SliderRow
        label={dx('diag.det.eyeClosure')}
        value={v?.eye_closure_s ?? 2}
        unit={dx('diag.raw.s')}
        min={0.5}
        max={5}
        step={0.5}
        onChange={(x) => update({ eye_closure_s: x })}
        disabled={!ready}
      />
      <SliderRow
        label={dx('diag.det.offroad')}
        value={v?.offroad_gaze_s ?? 2}
        unit={dx('diag.raw.s')}
        min={0.5}
        max={5}
        step={0.5}
        onChange={(x) => update({ offroad_gaze_s: x })}
        disabled={!ready}
      />
      <SliderRow
        label={dx('diag.det.phoneDuration')}
        value={v?.phone_s ?? 1}
        unit={dx('diag.raw.s')}
        min={0.5}
        max={5}
        step={0.5}
        onChange={(x) => update({ phone_s: x })}
        disabled={!ready}
      />
      {(['drowsiness', 'distraction', 'phone', 'physiology'] as const).map((d) => (
        <Row
          key={d}
          label={dx(`diag.det.${d}`)}
          disabled={!ready}
          right={
            <Toggle
              label={dx(`diag.det.${d}`)}
              value={v?.detectors[d] ?? true}
              disabled={!ready}
              onChange={(on) => update({ detectors: { [d]: on } as PiSettings['detectors'] })}
            />
          }
        />
      ))}
    </Section>
  );
}
