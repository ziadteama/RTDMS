/**
 * Platform BLE runtime permission request & inspection.
 * Android 12+ (API >= 31): BLUETOOTH_SCAN + BLUETOOTH_CONNECT.
 * Android <= 11: ACCESS_FINE_LOCATION.
 * iOS / Web / Jest: resolves true.
 */

import { PermissionsAndroid, Platform } from 'react-native';

export async function hasBlePermissions(): Promise<boolean> {
  if (Platform.OS !== 'android') return true;

  const version = Number(Platform.Version);
  if (version >= 31) {
    const [hasScan, hasConnect] = await Promise.all([
      PermissionsAndroid.check(PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN),
      PermissionsAndroid.check(PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT),
    ]);
    return hasScan && hasConnect;
  }

  return PermissionsAndroid.check(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);
}

export async function requestBlePermissions(): Promise<boolean> {
  if (Platform.OS !== 'android') return true;

  const version = Number(Platform.Version);
  if (version >= 31) {
    const results = await PermissionsAndroid.requestMultiple([
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
    ]);
    return (
      results[PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN] === PermissionsAndroid.RESULTS.GRANTED &&
      results[PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT] === PermissionsAndroid.RESULTS.GRANTED
    );
  }

  const result = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);
  return result === PermissionsAndroid.RESULTS.GRANTED;
}
