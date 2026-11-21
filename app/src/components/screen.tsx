import type { ReactNode } from 'react';
import { ScrollView, type ScrollViewProps } from 'react-native';

import { spacing, useTheme } from '@/theme';

/** Scrollable screen body under a native stack header / tab bar (safe areas handled natively). */
export function Screen({ children, style, contentContainerStyle, ...props }: ScrollViewProps & { children: ReactNode }) {
  const { colors } = useTheme();
  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
      style={[{ flex: 1, backgroundColor: colors.background }, style]}
      contentContainerStyle={[
        { padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xxxl },
        contentContainerStyle,
      ]}
      {...props}
    >
      {children}
    </ScrollView>
  );
}
