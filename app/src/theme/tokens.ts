import type { TextStyle } from 'react-native';

/** 4-pt grid. Row gap < group gap < section gap. */
export const spacing = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 20,
  full: 9999,
} as const;

/** Small fixed sizes: legend dots, timeline tracks, hairline-plus lines. */
export const size = { dot: 10, dotLarge: 12, line: 2, track: 20, trackLabel: 18 } as const;

/** Minimum touch target (Material 48 dp). */
export const touch = { min: 48, large: 64, huge: 96 } as const;

/**
 * Type ramp sized for a phone in a dashboard mount: read at arm's length, at a glance.
 * System font (Roboto / SF); numbers use tabular figures so values don't jitter at 5 Hz.
 */
export const type = {
  state: { fontSize: 44, lineHeight: 52, fontWeight: '800', letterSpacing: -0.5 },
  title: { fontSize: 28, lineHeight: 34, fontWeight: '700' },
  headline: { fontSize: 20, lineHeight: 26, fontWeight: '600' },
  body: { fontSize: 17, lineHeight: 24, fontWeight: '400' },
  label: { fontSize: 15, lineHeight: 20, fontWeight: '600' },
  caption: { fontSize: 13, lineHeight: 18, fontWeight: '400' },
  metric: { fontSize: 30, lineHeight: 36, fontWeight: '700', fontVariant: ['tabular-nums'] },
  metricSmall: { fontSize: 20, lineHeight: 26, fontWeight: '600', fontVariant: ['tabular-nums'] },
  countdown: { fontSize: 120, lineHeight: 132, fontWeight: '800', fontVariant: ['tabular-nums'] },
} as const satisfies Record<string, TextStyle>;

export type TypeVariant = keyof typeof type;

/** Durations (ms) and springs. Springs are critically damped-ish: no bounce for show. */
export const motion = {
  fast: 150,
  base: 250,
  slow: 400,
  /** State change on the live indicator (Alert → Drowsy). */
  stateSpring: { damping: 26, stiffness: 260, mass: 1 },
  /** Press feedback. */
  pressSpring: { damping: 30, stiffness: 500, mass: 0.6 },
  /** Max-alert pulse period. */
  pulse: 700,
} as const;
