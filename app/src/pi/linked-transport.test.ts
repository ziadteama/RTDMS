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
