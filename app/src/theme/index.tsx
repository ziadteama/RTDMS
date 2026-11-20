import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

import { palettes, type Palette, type Scheme } from './colors';
import { useSettings } from '@/state/settings';

export * from './tokens';
export type { Palette, Scheme } from './colors';
export { palettes } from './colors';

const ThemeContext = createContext<{ scheme: Scheme; colors: Palette }>({
  scheme: 'dark',
  colors: palettes.dark,
});

/** Theme setting: 'system' follows the OS, default is dark (night driving). */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const setting = useSettings((s) => s.theme);
  const os = useColorScheme();
  const scheme: Scheme = setting === 'system' ? (os === 'light' ? 'light' : 'dark') : setting;
  const value = useMemo(() => ({ scheme, colors: palettes[scheme] }), [scheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
