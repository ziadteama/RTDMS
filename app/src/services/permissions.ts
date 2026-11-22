import { Camera } from 'expo-camera';
import * as Location from 'expo-location';
import { PermissionsAndroid, Platform } from 'react-native';

export type PermissionKey = 'location' | 'notifications' | 'sms' | 'camera';
export type PermissionState = 'granted' | 'denied' | 'undetermined' | 'unsupported';

type AndroidPermission = (typeof PermissionsAndroid.PERMISSIONS)[keyof typeof PermissionsAndroid.PERMISSIONS];

async function android(pick: (p: typeof PermissionsAndroid.PERMISSIONS) => AndroidPermission[], ask: boolean): Promise<PermissionState> {
  // PermissionsAndroid does not exist on web / iOS: only touch it on Android.
  if (Platform.OS !== 'android') return 'unsupported';
  const list = pick(PermissionsAndroid.PERMISSIONS);
  if (ask) {
    const r = await PermissionsAndroid.requestMultiple(list);
    return Object.values(r).every((v) => v === PermissionsAndroid.RESULTS.GRANTED) ? 'granted' : 'denied';
  }
  const checks = await Promise.all(list.map((p) => PermissionsAndroid.check(p)));
  return checks.every(Boolean) ? 'granted' : 'undetermined';
}

export async function permission(key: PermissionKey, ask: boolean): Promise<PermissionState> {
  if (Platform.OS === 'web') return key === 'camera' ? 'granted' : 'unsupported';
  switch (key) {
    case 'location': {
      const r = ask ? await Location.requestForegroundPermissionsAsync() : await Location.getForegroundPermissionsAsync();
      return r.granted ? 'granted' : r.canAskAgain ? 'undetermined' : 'denied';
    }
    case 'camera': {
      try {
        if (!Camera || typeof Camera.requestCameraPermissionsAsync !== 'function') return 'granted';
        const r = ask ? await Camera.requestCameraPermissionsAsync() : await Camera.getCameraPermissionsAsync();
        return r.granted ? 'granted' : (ask || !r.canAskAgain ? 'denied' : 'undetermined');
      } catch {
        return 'granted';
      }
    }
    case 'notifications':
      if (Platform.OS === 'android' && Number(Platform.Version) < 33) return 'granted';
      return android((p) => [p.POST_NOTIFICATIONS], ask);
    case 'sms':
      return android((p) => [p.SEND_SMS, p.CALL_PHONE], ask);
  }
}
