import { memo } from 'react';
import { View } from 'react-native';
import { WebView } from 'react-native-webview';

import { radius, useTheme } from '@/theme';

import { Text } from './text';

/**
 * MJPEG live view. React Native's Image does not stream multipart MJPEG reliably on Android, so a
 * WebView shows `<img src=".../stream.mjpg">` (the spec's choice). stream.py only JPEG-encodes while
 * someone watches, so the view unmounts whenever it is hidden (driving lock, other tab).
 */
export const LiveView = memo(function LiveView({ url, emptyLabel }: { url: string | null; emptyLabel: string }) {
  const { colors } = useTheme();
  const box = { aspectRatio: 4 / 3, borderRadius: radius.md, overflow: 'hidden' as const, backgroundColor: colors.surface };
  if (!url)
    return (
      <View style={[box, { alignItems: 'center', justifyContent: 'center' }]}>
        <Text tone="tertiary">{emptyLabel}</Text>
      </View>
    );
  const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;height:100%;background:${colors.surface}}img{width:100%;height:100%;object-fit:contain}</style></head><body><img src="${url}" alt=""></body></html>`;
  return (
    <View style={box}>
      <WebView
        source={{ html, baseUrl: url }}
        originWhitelist={['*']}
        scrollEnabled={false}
        javaScriptEnabled={false}
        style={{ backgroundColor: colors.surface }}
        androidLayerType="hardware"
        accessibilityLabel={emptyLabel}
      />
    </View>
  );
});
