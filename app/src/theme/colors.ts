import type { AlertPattern } from '@/pi/types';

/**
 * One neutral palette + one semantic scale. Fixed light/dark pairs rather than Material You
 * dynamic colors: the theme is a user setting (dark-first for night driving), and alert colors
 * must mean the same thing on every phone. No decorative color anywhere.
 */
export type Palette = {
  background: string;
  surface: string;
  surfaceRaised: string;
  separator: string;
  text: string;
  textSecondary: string;
  textTertiary: string;
  /** Primary action: inverted neutral, not a brand hue. */
  action: string;
  onAction: string;
  /** Severity scale, index-aligned with fusion's AlertPattern. */
  alert: Record<AlertPattern, string>;
  /** Text/icon color on a filled alert surface. */
  onAlert: Record<AlertPattern, string>;
  /** Not connected / no data: a state, so it gets a token too. */
  unknown: string;
  scrim: string;
};

const dark: Palette = {
  background: '#0B0D0F',
  surface: '#14171A',
  surfaceRaised: '#1C2024',
  separator: '#2A2F35',
  text: '#F1F3F5',
  textSecondary: '#A5ADB5',
  textTertiary: '#6F7881',
  action: '#F1F3F5',
  onAction: '#0B0D0F',
  alert: {
    none: '#3FB97A',
    short_beep: '#E3C14B',
    repeated: '#F08A3C',
    continuous: '#EF5148',
    max: '#FF2E3A',
  },
  onAlert: {
    none: '#06140C',
    short_beep: '#1A1402',
    repeated: '#1D0C00',
    continuous: '#FFFFFF',
    max: '#FFFFFF',
  },
  unknown: '#6F7881',
  scrim: 'rgba(0,0,0,0.72)',
};

const light: Palette = {
  background: '#F5F6F7',
  surface: '#FFFFFF',
  surfaceRaised: '#ECEEF0',
  separator: '#D5DADF',
  text: '#0E1114',
  textSecondary: '#4D555D',
  textTertiary: '#5A626A',
  action: '#0E1114',
  onAction: '#FFFFFF',
  alert: {
    none: '#1C8A52',
    short_beep: '#8C6F00',
    repeated: '#B4560C',
    continuous: '#C42B23',
    max: '#B0001A',
  },
  onAlert: {
    none: '#FFFFFF',
    short_beep: '#FFFFFF',
    repeated: '#FFFFFF',
    continuous: '#FFFFFF',
    max: '#FFFFFF',
  },
  unknown: '#5A626A',
  scrim: 'rgba(0,0,0,0.5)',
};

export const palettes = { dark, light } as const;
export type Scheme = keyof typeof palettes;
