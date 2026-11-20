import { memo } from 'react';
import { View } from 'react-native';

import { radius, useTheme } from '@/theme';

import { Text } from './text';

// Web build: a plain <img> streams MJPEG natively in browsers.
export const LiveView = memo(function LiveView({ url, emptyLabel }: { url: string | null; emptyLabel: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ aspectRatio: 4 / 3, borderRadius: radius.md, overflow: 'hidden', backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' }}>
      {url ? (
        <img src={url} alt={emptyLabel} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
      ) : (
        <Text tone="tertiary">{emptyLabel}</Text>
      )}
    </View>
  );
});
