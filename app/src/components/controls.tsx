/**
 * Native controls from @expo/ui (Jetpack Compose on Android, SwiftUI on iOS). Each needs its own
 * Host; the Host gets the app theme (not the OS one), the text direction, and a neutral seed color
 * so Material You does not tint them purple.
 */
import { Host, Picker, Slider, Switch } from '@expo/ui';
import { I18nManager } from 'react-native';

import { useSettings } from '@/state/settings';
import { useTheme } from '@/theme';

function useHost() {
  const { scheme, colors } = useTheme();
  const rtl = useSettings((s) => s.language === 'ar') || I18nManager.isRTL;
  return { colorScheme: scheme, seedColor: colors.textSecondary, layoutDirection: rtl ? ('rightToLeft' as const) : ('leftToRight' as const) };
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
  return (
    <Host matchContents={{ vertical: true }} style={{ width: '100%' }} {...host}>
      <Slider value={value} onValueChange={onChange} min={min} max={max} step={step} disabled={disabled} />
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
  const host = useHost();
  return (
    <Host matchContents {...host}>
      <Picker selectedValue={value} onValueChange={(v) => onChange(v as T)} appearance="menu" enabled={!disabled} accessibilityLabel={label}>
        {options.map((o) => (
          <Picker.Item key={o.value} label={o.label} value={o.value} />
        ))}
      </Picker>
    </Host>
  );
}
