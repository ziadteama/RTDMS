import type { BleManager } from 'react-native-ble-plx';

import { PlxBleLink } from './link';
import { isAuthError } from './link-util';
import { FakeDevice, MockBleManager } from './link-test-support';
import { CHAR_UUID } from './uuids';

const target = { name: 'RTDMS-Pi', token: 'test-token-for-pairing' };
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
let device: FakeDevice;
let manager: MockBleManager;
let link: PlxBleLink;
const flush = () => jest.advanceTimersByTimeAsync(30);
beforeEach(() => {
  jest.useFakeTimers();
  device = new FakeDevice();
  manager = new MockBleManager(device);
  link = new PlxBleLink(() => manager as unknown as BleManager);
});
afterEach(() => { link.stop(); jest.useRealTimers(); jest.restoreAllMocks(); });

test.each(['command', 'incident'] as const)('%s holds the shared slot before any native write', async (first) => {
  link.start(target);
  await flush();
  const pendingWrite = deferred<void>();
  const write = jest.spyOn(device, 'writeCharacteristicWithResponseForService').mockReturnValue(pendingWrite.promise);
  const pending = link[first]({ cmd: 'restart' });
  for (const kind of ['command', 'incident'] as const) await expect(link[kind]({})).rejects.toThrow('busy');
  expect(write).toHaveBeenCalledTimes(1);
  device.emitMonitor(CHAR_UUID.RESULT, { ok: true, id: 'ambiguous-id' });
  await expect(link.incident({})).rejects.toThrow('busy'); // native write is still pending
  pendingWrite.resolve();
  await expect(pending).resolves.toEqual({ ok: true, id: 'ambiguous-id' });
  expect(jest.getTimerCount()).toBe(1); // Connected clock refresh remains; result timer is gone.
});

test.each(['command', 'incident'] as const)('%s cancels a failed write registration and timer', async (kind) => {
  link.start(target);
  await flush();
  const write = jest.spyOn(device, 'writeCharacteristicWithResponseForService').mockRejectedValueOnce(new Error('write failed'));
  await expect(link[kind]({})).rejects.toThrow('write failed');
  expect(jest.getTimerCount()).toBe(1); // Connected clock refresh remains; result timer is gone.
  const next = link[kind]({});
  device.emitMonitor(CHAR_UUID.RESULT, { ok: true });
  await expect(next).resolves.toEqual({ ok: true });
  expect(write).toHaveBeenCalledTimes(2);
});

test('encoding failure never reserves a slot or writes', async () => {
  link.start(target);
  await flush();
  const write = jest.spyOn(device, 'writeCharacteristicWithResponseForService');
  await expect(link.command({ text: 'x'.repeat(600) })).rejects.toThrow('512');
  expect(write).not.toHaveBeenCalled();
  expect(jest.getTimerCount()).toBe(1); // Connected clock refresh remains; result timer is gone.
  const next = link.incident({});
  device.emitMonitor(CHAR_UUID.RESULT, { ok: true });
  await expect(next).resolves.toEqual({ ok: true });
});

test('timeout while native write is pending is handled immediately', async () => {
  link.start(target);
  await flush();
  const pendingWrite = deferred<void>();
  jest.spyOn(device, 'writeCharacteristicWithResponseForService').mockReturnValue(pendingWrite.promise);
  const result = expect(link.command({}, 50)).rejects.toThrow('timed out');
  await jest.advanceTimersByTimeAsync(51);
  await result;
  await expect(link.incident({})).rejects.toThrow('busy');
  pendingWrite.reject(new Error('late native failure'));
  await flush();
  expect(jest.getTimerCount()).toBe(1); // Connected clock refresh remains; result timer is gone.
});

test.each(['mtu', 'discovery', 'auth', 'clock'] as const)('stop during %s prevents setup from reviving the session', async (stage) => {
  const pending = deferred<void>();
  if (stage === 'mtu') jest.spyOn(device, 'requestMTU').mockImplementation(async () => { await pending.promise; return device; });
  if (stage === 'discovery') jest.spyOn(device, 'discoverAllServicesAndCharacteristics').mockImplementation(async () => { await pending.promise; return device; });
  if (stage === 'auth' || stage === 'clock') {
    const original = device.writeCharacteristicWithResponseForService.bind(device);
    jest.spyOn(device, 'writeCharacteristicWithResponseForService').mockImplementation(async (s, c, v) => {
      await original(s, c, v);
      if (c === (stage === 'auth' ? CHAR_UUID.AUTH : CHAR_UUID.CLOCK)) await pending.promise;
    });
  }
  const cancel = jest.spyOn(manager, 'cancelDeviceConnection');
  link.start(target);
  await flush();
  const oldCallback = device.disconnectCb;
  link.stop();
  pending.resolve();
  await flush();
  oldCallback?.(null, device);
  expect(link.state).toBe('idle');
  expect(device.monitors.size).toBe(0);
  expect(device.disconnectCb).toBeNull();
  expect(cancel).toHaveBeenCalledWith(device.id);
  expect(jest.getTimerCount()).toBe(0);
});

test('stop cancels the device while connectToDevice is still pending', async () => {
  const pending = deferred<FakeDevice>();
  jest.spyOn(manager, 'connectToDevice').mockReturnValue(pending.promise);
  const cancel = jest.spyOn(manager, 'cancelDeviceConnection');
  link.start({ ...target, deviceId: device.id });
  await flush();
  link.stop();
  expect(cancel).toHaveBeenCalledWith(device.id);
  pending.resolve(device);
  await flush();
  expect(link.state).toBe('idle');
  expect(device.disconnectCb).toBeNull();
  expect(device.writes).toHaveLength(0);
});

test('a new target invalidates old setup and disconnect callbacks', async () => {
  const pending = deferred<void>();
  const original = device.writeCharacteristicWithResponseForService.bind(device);
  jest.spyOn(device, 'writeCharacteristicWithResponseForService').mockImplementation(async (s, c, v) => {
    await original(s, c, v);
    if (c === CHAR_UUID.CLOCK) await pending.promise;
  });
  link.start(target);
  await flush();
  const oldCallback = device.disconnectCb;
  const next = new FakeDevice();
  next.id = 'next-device';
  manager.devices.set(next.id, next);
  link.start({ ...target, deviceId: next.id });
  await flush();
  pending.resolve();
  oldCallback?.(null, device);
  await flush();
  expect(link.state).toBe('online');
  expect(link.deviceId).toBe(next.id);
  expect(device.monitors.size).toBe(0);
  expect(next.monitors.size).toBe(4);
  next.simulateDisconnect();
  expect(next.disconnectCb).toBeNull();
  expect(next.monitors.size).toBe(0);
});

test.each([5, 8, 14])('ATT %s rejection retries at 15 seconds and can recover', async (attErrorCode) => {
  const original = device.writeCharacteristicWithResponseForService.bind(device);
  const write = jest.spyOn(device, 'writeCharacteristicWithResponseForService').mockRejectedValue({ errorCode: 401, attErrorCode });
  link.start({ ...target, deviceId: device.id });
  await flush();
  expect(link.lastError).toBe('auth');
  expect(link.state).toBe('offline');
  expect(device.disconnectCb).toBeNull();
  await jest.advanceTimersByTimeAsync(14900);
  expect(write).toHaveBeenCalledTimes(1);
  write.mockImplementation(original);
  await jest.advanceTimersByTimeAsync(100);
  expect(link.state).toBe('online');
  expect(link.lastError).toBeNull();
});

test.each([new Error('disconnected'), { errorCode: 401 }, { errorCode: 201 }, { attErrorCode: 13 }])(
  'non-auth failures reconnect with normal backoff', async (error) => {
    jest.spyOn(Math, 'random').mockReturnValue(0.5);
    jest.spyOn(device, 'writeCharacteristicWithResponseForService').mockRejectedValueOnce(error);
    link.start({ ...target, deviceId: device.id });
    await flush();
    expect(link.lastError).not.toBe('auth');
    expect(link.state).toBe('offline');
    await jest.advanceTimersByTimeAsync(1000);
    expect(link.state).toBe('online');
  },
);

test('auth detection uses structured ATT errors, not message text', () => {
  expect(isAuthError(new Error('auth failed'))).toBe(false);
  expect(isAuthError({ errorCode: 5 })).toBe(true);
  expect(isAuthError({ errorCode: 401, attErrorCode: '0x0e' })).toBe(true);
});
