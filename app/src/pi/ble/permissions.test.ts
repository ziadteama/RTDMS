import { PermissionsAndroid, Platform } from 'react-native';

import { hasBlePermissions, requestBlePermissions } from './permissions';

jest.mock('react-native', () => {
  const checkMock = jest.fn();
  const requestMock = jest.fn();
  const requestMultipleMock = jest.fn();

  return {
    Platform: {
      OS: 'android',
      Version: 33,
    },
    PermissionsAndroid: {
      PERMISSIONS: {
        BLUETOOTH_SCAN: 'android.permission.BLUETOOTH_SCAN',
        BLUETOOTH_CONNECT: 'android.permission.BLUETOOTH_CONNECT',
        ACCESS_FINE_LOCATION: 'android.permission.ACCESS_FINE_LOCATION',
      },
      RESULTS: {
        GRANTED: 'granted',
        DENIED: 'denied',
      },
      check: checkMock,
      request: requestMock,
      requestMultiple: requestMultipleMock,
    },
  };
});

describe('BLE permissions', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Non-Android platforms', () => {
    it('always resolves true on iOS and Web', async () => {
      (Platform as { OS: string }).OS = 'ios';
      expect(await hasBlePermissions()).toBe(true);
      expect(await requestBlePermissions()).toBe(true);
      expect(PermissionsAndroid.check).not.toHaveBeenCalled();
      expect(PermissionsAndroid.requestMultiple).not.toHaveBeenCalled();
    });
  });

  describe('Android 12+ (API >= 31)', () => {
    beforeEach(() => {
      (Platform as { OS: string; Version: number }).OS = 'android';
      (Platform as { OS: string; Version: number }).Version = 33;
    });

    it('checks BLUETOOTH_SCAN and BLUETOOTH_CONNECT permissions', async () => {
      (PermissionsAndroid.check as jest.Mock).mockResolvedValue(true);

      const has = await hasBlePermissions();
      expect(has).toBe(true);
      expect(PermissionsAndroid.check).toHaveBeenCalledWith(PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN);
      expect(PermissionsAndroid.check).toHaveBeenCalledWith(PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT);
    });

    it('returns false if any permission is missing in check', async () => {
      (PermissionsAndroid.check as jest.Mock)
        .mockResolvedValueOnce(true)
        .mockResolvedValueOnce(false);

      const has = await hasBlePermissions();
      expect(has).toBe(false);
    });

    it('requests BLUETOOTH_SCAN and BLUETOOTH_CONNECT via requestMultiple', async () => {
      (PermissionsAndroid.requestMultiple as jest.Mock).mockResolvedValue({
        [PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN]: PermissionsAndroid.RESULTS.GRANTED,
        [PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT]: PermissionsAndroid.RESULTS.GRANTED,
      });

      const granted = await requestBlePermissions();
      expect(granted).toBe(true);
      expect(PermissionsAndroid.requestMultiple).toHaveBeenCalledWith([
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
        PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      ]);
    });

    it('returns false if any permission is denied', async () => {
      (PermissionsAndroid.requestMultiple as jest.Mock).mockResolvedValue({
        [PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN]: PermissionsAndroid.RESULTS.GRANTED,
        [PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT]: PermissionsAndroid.RESULTS.DENIED,
      });

      const granted = await requestBlePermissions();
      expect(granted).toBe(false);
    });
  });

  describe('Android <= 11 (API < 31)', () => {
    beforeEach(() => {
      (Platform as { OS: string; Version: number }).OS = 'android';
      (Platform as { OS: string; Version: number }).Version = 29;
    });

    it('checks ACCESS_FINE_LOCATION on legacy Android', async () => {
      (PermissionsAndroid.check as jest.Mock).mockResolvedValue(true);

      const has = await hasBlePermissions();
      expect(has).toBe(true);
      expect(PermissionsAndroid.check).toHaveBeenCalledWith(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);
    });

    it('requests ACCESS_FINE_LOCATION on legacy Android', async () => {
      (PermissionsAndroid.request as jest.Mock).mockResolvedValue(PermissionsAndroid.RESULTS.GRANTED);

      const granted = await requestBlePermissions();
      expect(granted).toBe(true);
      expect(PermissionsAndroid.request).toHaveBeenCalledWith(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION);
    });
  });
});
