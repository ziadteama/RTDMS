import { requireNativeView } from 'expo';
import React, { useCallback } from 'react';
import { Platform, type StyleProp, type ViewStyle } from 'react-native';

import type { FaceSample } from './SahiNative.types';

export type SahiFaceViewProps = {
  active?: boolean;
  style?: StyleProp<ViewStyle>;
  onFace: (sample: FaceSample) => void;
};

type NativeProps = {
  active?: boolean;
  style?: StyleProp<ViewStyle>;
  onFace?: (event: { nativeEvent: FaceSample }) => void;
};

let NativeView: React.ComponentType<NativeProps> | null = null;
if (Platform.OS === 'android') {
  try {
    NativeView = requireNativeView<NativeProps>('SahiNative', 'SahiFaceView');
  } catch {
    try {
      NativeView = requireNativeView<NativeProps>('SahiNative');
    } catch {
      NativeView = null;
    }
  }
}

export function isFaceViewAvailable(): boolean {
  return NativeView !== null;
}

export function SahiFaceView({ active = true, style, onFace }: SahiFaceViewProps) {
  const handleFace = useCallback(
    (event: { nativeEvent: FaceSample }) => {
      onFace(event.nativeEvent);
    },
    [onFace]
  );

  if (!NativeView) {
    return null;
  }

  return <NativeView active={active} style={style} onFace={handleFace} />;
}
