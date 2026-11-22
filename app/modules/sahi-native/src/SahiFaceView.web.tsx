import type { StyleProp, ViewStyle } from 'react-native';

import type { FaceSample } from './SahiNative.types';

export type SahiFaceViewProps = {
  active?: boolean;
  style?: StyleProp<ViewStyle>;
  onFace: (sample: FaceSample) => void;
};

export function isFaceViewAvailable(): boolean {
  return false;
}

export function SahiFaceView(_props: SahiFaceViewProps) {
  return null;
}
