import { SymbolView } from 'expo-symbols';
import type { SFSymbol } from 'sf-symbols-typescript';

import { useTheme } from '@/theme';

/** One icon set: SF Symbols on iOS, Material Symbols on Android and web (bundled font, offline). */
const ICONS = {
  live: { ios: 'video', android: 'videocam' },
  trips: { ios: 'road.lanes', android: 'route' },
  health: { ios: 'cpu', android: 'memory' },
  settings: { ios: 'gearshape', android: 'settings' },
  wifiOff: { ios: 'wifi.slash', android: 'wifi_off' },
  wifi: { ios: 'wifi', android: 'wifi' },
  play: { ios: 'play.rectangle', android: 'smart_display' },
  pause: { ios: 'pause.circle', android: 'pause_circle' },
  gps: { ios: 'location.slash', android: 'location_off' },
  info: { ios: 'info.circle', android: 'info' },
  warning: { ios: 'exclamationmark.triangle', android: 'warning' },
  chevron: { ios: 'chevron.right', android: 'chevron_right' },
  check: { ios: 'checkmark.circle', android: 'check_circle' },
  close: { ios: 'xmark.circle', android: 'cancel' },
  add: { ios: 'plus', android: 'add' },
  delete: { ios: 'trash', android: 'delete' },
  phone: { ios: 'iphone', android: 'smartphone' },
  call: { ios: 'phone', android: 'call' },
  sms: { ios: 'message', android: 'sms' },
  eye: { ios: 'eye', android: 'visibility' },
  heart: { ios: 'heart', android: 'favorite' },
  qr: { ios: 'qrcode.viewfinder', android: 'qr_code_scanner' },
  location: { ios: 'location', android: 'location_on' },
  notifications: { ios: 'bell', android: 'notifications' },
  camera: { ios: 'camera', android: 'photo_camera' },
  bluetooth: { ios: 'antenna.radiowaves.left.and.right', android: 'bluetooth' },
  crash: { ios: 'car.side.rear.and.collision.and.car.side.front', android: 'car_crash' },
  sos: { ios: 'sos', android: 'sos' },
  download: { ios: 'arrow.down.circle', android: 'download' },
  restart: { ios: 'arrow.clockwise', android: 'restart_alt' },
  power: { ios: 'power', android: 'power_settings_new' },
  person: { ios: 'person', android: 'person' },
  speed: { ios: 'speedometer', android: 'speed' },
} as const satisfies Record<string, { ios: SFSymbol; android: string }>;

export type IconName = keyof typeof ICONS;

export function Icon({ name, size = 24, color }: { name: IconName; size?: number; color?: string }) {
  const { colors } = useTheme();
  const i = ICONS[name];
  return (
    <SymbolView
      name={{ ios: i.ios, android: i.android as never, web: i.android as never }}
      size={size}
      tintColor={color ?? colors.text}
    />
  );
}

export const iconNames = ICONS;
