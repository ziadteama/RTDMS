import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { SahiFaceView, type FaceSample } from './adapters';

export function CameraStage({
  isNative,
  onFace,
  hidden,
  style,
}: {
  isNative: boolean;
  onFace: (sample: FaceSample) => void;
  hidden?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  if (!isNative) return null;

  return (
    <View
      pointerEvents="none"
      style={[hidden ? styles.hidden : styles.stage, style]}
    >
      <SahiFaceView active style={StyleSheet.absoluteFill} onFace={onFace} />
    </View>
  );
}

const styles = StyleSheet.create({
  stage: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  hidden: {
    position: 'absolute',
    width: 1,
    height: 1,
    opacity: 0,
    overflow: 'hidden',
  },
});
