import { PiHttpError, type PiTransport } from '../transport';
import { FakeBleLink } from './fake-link';
import { BleTransport } from './transport';

class MockHttpTransport implements PiTransport {
  readonly kind = 'http';
  getCalls: { path: string; timeoutMs?: number }[] = [];
  sendCalls: { method: string; path: string; body?: unknown; timeoutMs?: number }[] = [];

  async get(path: string, timeoutMs?: number): Promise<unknown> {
    this.getCalls.push({ path, timeoutMs });
    if (path === '/incidents') return [{ id: 'inc-1' }];
    return { http: true };
  }

  async send(method: 'POST' | 'PUT', path: string, body?: unknown, timeoutMs?: number): Promise<unknown> {
    this.sendCalls.push({ method, path, body, timeoutMs });
    return { ok: true, http: true };
  }

  streamUrl(): string {
    return 'http://pi:8080/stream.mjpg';
  }

  clip(id: string) {
    return { uri: `http://pi:8080/incidents/${id}/clip.mp4` };
  }

  async frames(_id: string) {
    return [];
  }
}

describe('BleTransport', () => {
  let fakeLink: FakeBleLink;
  let mockHttp: MockHttpTransport;
  let transport: BleTransport;

  beforeEach(() => {
    fakeLink = new FakeBleLink();
    fakeLink.setState('online');
    mockHttp = new MockHttpTransport();
    transport = new BleTransport(fakeLink, mockHttp);
  });

  afterEach(() => {
    transport.dispose();
  });

  describe('cached notify endpoints (/status, /alert, /physio)', () => {
    it('throws when no notify has arrived yet', async () => {
      await expect(transport.get('/status')).rejects.toThrow(/no cached status/);
      await expect(transport.get('/alert')).rejects.toThrow(/no cached alert/);
      await expect(transport.get('/physio')).rejects.toThrow(/no cached physio/);
    });

    it('returns latest notified values after emits', async () => {
      const statusObj = { fps: 15, face: true, state: 'alert' };
      const alertObj = { pattern: 'short_beep', reasons: ['distracted'], t: 100 };
      const physioObj = { hr_bpm: 80, watch_connected: true, t: 100 };

      fakeLink.emit('status', statusObj);
      fakeLink.emit('alert', alertObj);
      fakeLink.emit('physio', physioObj);

      await expect(transport.get('/status')).resolves.toEqual(statusObj);
      await expect(transport.get('/alert')).resolves.toEqual(alertObj);
      await expect(transport.get('/physio')).resolves.toEqual(physioObj);
    });
  });

  describe('read / write characteristics', () => {
    it('reads health and settings over BLE', async () => {
      fakeLink.handlers.health = () => ({ cpu_pct: 20 });
      fakeLink.handlers.settings = () => ({ profile: 'default' });

      await expect(transport.get('/health')).resolves.toEqual({ cpu_pct: 20 });
      await expect(transport.get('/settings')).resolves.toEqual({ profile: 'default' });
    });

    it('writes settings and re-reads the updated object', async () => {
      let currentSettings = { profile: 'default', sensitivity: 'normal' };
      fakeLink.handlers.settings = () => currentSettings;
      fakeLink.writeSettings = async (body) => {
        currentSettings = { ...currentSettings, ...(body as object) };
      };

      const updated = await transport.send('PUT', '/settings', { sensitivity: 'high' });
      expect(updated).toEqual({ profile: 'default', sensitivity: 'high' });
    });
  });

  describe('commands & incidents', () => {
    it('sends test_alert via command', async () => {
      fakeLink.handlers.command = (b) => {
        expect(b).toEqual({ cmd: 'test_alert', pattern: 'max' });
        return { ok: true };
      };

      const res = await transport.send('POST', '/test_alert', { pattern: 'max' });
      expect(res).toEqual({ ok: true });
    });

    it('sends calibrate without body as plain calibrate command', async () => {
      fakeLink.handlers.command = (b) => {
        expect(b).toEqual({ cmd: 'calibrate' });
        return { ok: true };
      };

      const res = await transport.send('POST', '/calibrate');
      expect(res).toEqual({ ok: true });
    });

    it('sends calibrate with profile in body', async () => {
      const profile = { closed_ratio: 0.35, ear_open: 0.28 };
      fakeLink.handlers.command = (b) => {
        expect(b).toEqual({ cmd: 'calibrate', profile });
        return { ok: true };
      };

      const res = await transport.send('POST', '/calibrate', profile);
      expect(res).toEqual({ ok: true });
    });

    it('sends incident via incident link method', async () => {
      const incReq = { t_crash: 1234567, g_peak: 5.5 };
      fakeLink.handlers.incident = (b) => {
        expect(b).toEqual(incReq);
        return { ok: true, id: 'inc-123' };
      };

      const res = await transport.send('POST', '/incident', incReq);
      expect(res).toEqual({ ok: true, id: 'inc-123' });
    });

    it('throws PiHttpError(400, path) when command returns ok: false', async () => {
      fakeLink.handlers.command = () => ({ ok: false, error: 'rejected' });

      await expect(transport.send('POST', '/calibrate')).rejects.toThrow(PiHttpError);
      await expect(transport.send('POST', '/calibrate')).rejects.toMatchObject({
        status: 400,
      });
    });

    it('throws PiHttpError(400, path) when incident returns ok: false', async () => {
      fakeLink.handlers.incident = () => ({ ok: false, error: 'invalid crash time' });

      await expect(transport.send('POST', '/incident', { t_crash: 0, g_peak: 1 })).rejects.toThrow(PiHttpError);
    });
  });

  describe('delegation to HTTP transport', () => {
    it('delegates unknown GET paths and /incidents to HTTP transport', async () => {
      const incidents = await transport.get('/incidents');
      expect(incidents).toEqual([{ id: 'inc-1' }]);
      expect(mockHttp.getCalls).toEqual([{ path: '/incidents', timeoutMs: undefined }]);
    });

    it('delegates system POST/PUT to HTTP transport', async () => {
      await transport.send('POST', '/system/reboot', { force: true });
      expect(mockHttp.sendCalls).toEqual([
        { method: 'POST', path: '/system/reboot', body: { force: true }, timeoutMs: undefined },
      ]);
    });

    it('delegates streamUrl, clip, and frames to HTTP transport', async () => {
      expect(transport.streamUrl()).toBe('http://pi:8080/stream.mjpg');
      expect(transport.clip('123')).toEqual({ uri: 'http://pi:8080/incidents/123/clip.mp4' });
      await expect(transport.frames('123')).resolves.toEqual([]);
    });
  });
});
