import type { Palette } from '@/theme';

/** Score bands reuse the alert scale (green / amber / red): color still means severity. */
export function scoreColor(score: number | null, colors: Palette): string {
  if (score === null) return colors.unknown;
  if (score >= 80) return colors.alert.none;
  if (score >= 60) return colors.alert.short_beep;
  return colors.alert.continuous;
}
