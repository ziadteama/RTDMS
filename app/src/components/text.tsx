import { Text as RNText, type TextProps } from 'react-native';

import { type, useTheme, type TypeVariant } from '@/theme';

export type Tone = 'primary' | 'secondary' | 'tertiary';

/** The only text primitive: screens never set fontSize or colors directly. */
export function Text({
  variant = 'body',
  tone = 'primary',
  color,
  align,
  style,
  ...props
}: TextProps & { variant?: TypeVariant; tone?: Tone; color?: string; align?: 'auto' | 'center' }) {
  const { colors } = useTheme();
  const toneColor = tone === 'primary' ? colors.text : tone === 'secondary' ? colors.textSecondary : colors.textTertiary;
  return <RNText style={[type[variant], { color: color ?? toneColor, textAlign: align }, style]} {...props} />;
}
