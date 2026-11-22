/**
 * Switch and slider from @expo/ui. Each native control needs its own
 * Host; the Host gets the app theme (not the OS one), and a neutral seed color
 * so Material You does not tint them purple.
 */
import { Host, Slider, Switch } from '@expo/ui';
import { useState } from 'react';
import { Pressable, View } from 'react-native';

import { spacing, touch, useTheme } from '@/theme';

import { ChoiceSheet } from './choice-sheet';
import { Icon } from './icon';
import { Text } from './text';

function useHost() {
  const { scheme, colors } = useTheme();
  return { colorScheme: scheme, seedColor: colors.textSecondary, layoutDirection: 'leftToRight' as const };
}

export function Toggle({ value, onChange, label, disabled }: { value: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  const host = useHost();
  return (
    <Host matchContents {...host}>
      <Switch value={value} onValueChange={onChange} disabled={disabled} testID={label} />
    </Host>
  );
}

export function SliderControl({
  value,
  onChange,
  min,
  max,
  step,
  disabled,
}: {
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
}) {
  const host = useHost();
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  const change = (v: number) => {
    let next = v;
    if (step !== undefined && step > 0 && Number.isFinite(step)) {
      const [coefficient = '', exponent = '0'] = String(step).split('e');
      const decimals = Math.min(15, Math.max(0, (coefficient.split('.')[1]?.length ?? 0) - Number(exponent)));
      next = Number((Math.round(v / step) * step).toFixed(decimals));
    }
    next = clamp(next);
    if (next !== value) onChange(next);
  };
  return (
    <Host matchContents={{ vertical: true }} style={{ width: '100%' }} {...host}>
      <Slider value={clamp(value)} onValueChange={change} min={min} max={max} disabled={disabled} />
    </Host>
  );
}

export function Choice<T extends string>({
  value,
  options,
  onChange,
  label,
  disabled,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value)?.label ?? value;
  return (
    <>
      <Pressable
        onPress={() => setOpen(true)} disabled={disabled}
        accessibilityRole="button" accessibilityLabel={label}
        accessibilityValue={{ text: selected }}
        accessibilityState={{ disabled: !!disabled, expanded: open }}
        style={({ pressed }) => ({
          minHeight: touch.min, minWidth: touch.min, maxWidth: '100%',
          flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: spacing.xs,
          opacity: disabled ? 0.45 : pressed ? 0.7 : 1,
        })}
      >
        <Text tone="secondary" numberOfLines={1} ellipsizeMode="tail" style={{ flexShrink: 1 }}>{selected}</Text>
        <View style={{ transform: [{ rotate: '90deg' }] }}>
          <Icon name="chevron" size={20} color={colors.textSecondary} />
        </View>
      </Pressable>
      {open && !disabled ? (
        <ChoiceSheet label={label} value={value} options={options} onChange={onChange} onClose={() => setOpen(false)} />
      ) : null}
    </>
  );
}
