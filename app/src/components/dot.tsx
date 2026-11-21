import { View } from 'react-native';

import { radius, size as sizes } from '@/theme';

/** A legend dot: the color carries the meaning (alert pattern, event kind). */
export function Dot({ color, large }: { color: string; large?: boolean }) {
  const d = large ? sizes.dotLarge : sizes.dot;
  return <View style={{ width: d, height: d, borderRadius: radius.full, backgroundColor: color }} />;
}
