import { useSecure } from '@/state/secure';

import { FakeBleLink } from './ble/fake-link';
import { LinkedTransport } from './linked-transport';
import { HttpTransport } from './transport';

jest.mock('expo-secure-store', () => ({ getItem: jest.fn(() => null), setItem: jest.fn() }));
let fetchMock: jest.Mock;
beforeEach(() => {
  fetchMock = jest.fn(async () => ({ ok: true, json: async () => ({}), text: async () => '' }));
  global.fetch = fetchMock as unknown as typeof fetch;
  useSecure.setState({ piToken: null });
});
afterEach(() => useSecure.setState({ piToken: null }));

test('HTTP GET, writes, and frame downloads use the current token', async () => {
  let token: string | null = 'first-test-token';
  const t = new HttpTransport('http://pi', () => token);
  await t.get('/status');
  await t.send('PUT', '/settings', { sensitivity: 'high' });
  token = 'rotated-test-token';
  await t.send('POST', '/incident', {});
  await t.frames('id');
  expect(fetchMock.mock.calls.map(([, init]) => init.headers)).toEqual([
    { Authorization: 'Bearer first-test-token' },
    { Authorization: 'Bearer first-test-token', 'Content-Type': 'application/json' },
    { Authorization: 'Bearer rotated-test-token', 'Content-Type': 'application/json' },
    { Authorization: 'Bearer rotated-test-token' },
  ]);
  token = null;
  await t.get('/status');
  expect(fetchMock.mock.lastCall?.[1].headers).toBeUndefined();
});

test('HTTP remains compatible without a token getter', async () => {
  const t = new HttpTransport('http://pi');
  await t.get('/status');
  expect(fetchMock.mock.lastCall?.[1].headers).toBeUndefined();
  await t.send('POST', '/calibrate');
  expect(fetchMock.mock.lastCall?.[1].headers).toEqual({ 'Content-Type': 'application/json' });
});

test('LinkedTransport reads secure token on each fallback request', async () => {
  const link = new FakeBleLink();
  link.setState('online');
  const t = new LinkedTransport('http://pi', link);
  useSecure.setState({ piToken: 'secure-test-token' });
  await t.get('/status'); // no cached BLE notification: retry on HTTP
  expect(fetchMock.mock.lastCall?.[1].headers.Authorization).toBe('Bearer secure-test-token');
  link.setState('offline');
  useSecure.setState({ piToken: 'new-test-token' });
  await t.send('POST', '/calibrate');
  expect(fetchMock.mock.lastCall?.[1].headers.Authorization).toBe('Bearer new-test-token');
  expect(t.streamUrl()).toBe('http://pi/stream.mjpg');
  expect(t.clip('id')).toEqual({ uri: 'http://pi/incidents/id/clip.mp4' });
  t.dispose();
});
