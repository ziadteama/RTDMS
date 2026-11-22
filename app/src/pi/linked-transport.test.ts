import { FakeBleLink } from './ble/fake-link';
import { LinkedTransport } from './linked-transport';
import { PiHttpError } from './transport';

const mockBle = { get: jest.fn(), send: jest.fn(), dispose: jest.fn() };
jest.mock('./ble/transport', () => ({ BleTransport: jest.fn(() => mockBle) }));

let fetchMock: jest.Mock;
beforeEach(() => {
  jest.clearAllMocks();
  fetchMock = jest.fn(async () => ({ ok: true, json: async () => ({ from: 'http' }) }));
  global.fetch = fetchMock as unknown as typeof fetch;
});

const make = (state: 'online' | 'offline') => {
  const link = new FakeBleLink();
  link.setState(state);
  return { link, t: new LinkedTransport('http://pi.test:8080', link) };
};

describe('LinkedTransport', () => {
  it('uses BLE while online and reports kind ble', async () => {
    const { t } = make('online');
    mockBle.get.mockResolvedValue({ from: 'ble' });
    expect(t.kind).toBe('ble');
    expect(await t.get('/status')).toEqual({ from: 'ble' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('uses HTTP when the link is not online and reports kind http', async () => {
    const { t } = make('offline');
    expect(t.kind).toBe('http');
    expect(await t.get('/status')).toEqual({ from: 'http' });
    expect(await t.send('POST', '/test_alert', { pattern: 'max' })).toEqual({ from: 'http' });
    expect(mockBle.get).not.toHaveBeenCalled();
    expect(mockBle.send).not.toHaveBeenCalled();
  });

  it('follows the link state live', () => {
    const { link, t } = make('offline');
    link.setState('online');
    expect(t.kind).toBe('ble');
    link.setState('offline');
    expect(t.kind).toBe('http');
  });

  it('retries once over HTTP when a BLE call rejects with a non-HTTP error', async () => {
    const { t } = make('online');
    mockBle.send.mockRejectedValue(new Error('ble: link lost'));
    expect(await t.send('PUT', '/settings', { sensitivity: 'high' })).toEqual({ from: 'http' });
    expect(mockBle.send).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('passes a PiHttpError through without a second try', async () => {
    const { t } = make('online');
    mockBle.get.mockRejectedValue(new PiHttpError(404, '/physio'));
    await expect(t.get('/physio')).rejects.toBeInstanceOf(PiHttpError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('keeps video and incident files on HTTP and disposes the BLE side', () => {
    const { t } = make('online');
    expect(t.streamUrl()).toBe('http://pi.test:8080/stream.mjpg');
    expect(t.clip('a b')).toEqual({ uri: 'http://pi.test:8080/incidents/a%20b/clip.mp4' });
    t.dispose();
    expect(mockBle.dispose).toHaveBeenCalled();
  });
});

it.each(['/calibrate', '/test_alert', '/system/restart', '/system/shutdown', '/incident', '/other'])(
  'does not replay POST %s after an ambiguous BLE failure', async (path) => {
    const { t } = make('online');
    mockBle.send.mockRejectedValue(new Error('lost result'));
    await expect(t.send('POST', path, {})).rejects.toThrow('lost result');
    expect(fetchMock).not.toHaveBeenCalled();
  },
);

it('retries an incident only when it has a nonempty client_id', async () => {
  const { t } = make('online');
  mockBle.send.mockRejectedValue(new Error('lost result'));
  for (const client_id of [undefined, null, '', 1]) {
    await expect(t.send('POST', '/incident', { client_id })).rejects.toThrow('lost result');
  }
  expect(fetchMock).not.toHaveBeenCalled();
  const body = { client_id: 'dedup-id', t_crash: 123 };
  await expect(t.send('POST', '/incident', body)).resolves.toEqual({ from: 'http' });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/incident'), expect.objectContaining({ body: JSON.stringify(body) }));
});

it('retries reads once, but does not retry arbitrary PUTs', async () => {
  const { t } = make('online');
  mockBle.get.mockRejectedValue(new Error('lost link'));
  await expect(t.get('/status')).resolves.toEqual({ from: 'http' });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  fetchMock.mockClear();
  mockBle.send.mockRejectedValue(new Error('lost link'));
  await expect(t.send('PUT', '/other')).rejects.toThrow('lost link');
  expect(fetchMock).not.toHaveBeenCalled();
});
