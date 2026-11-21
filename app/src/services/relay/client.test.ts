import { createRelayClient } from './client';
import type { RegisterContact, SosRequestPayload } from './types';

describe('RelayClient', () => {
  const fakeConfig = () => ({
    baseUrl: 'https://relay.example.com',
    apiKey: 'test-api-key',
  });
  const fakeInstallId = () => 'test-install-uuid-1234';

  it('sends proper headers including Bearer and X-Install-Id for register', async () => {
    let capturedUrl = '';
    let capturedInit: RequestInit | undefined;

    const fakeFetch: typeof fetch = async (input, init) => {
      capturedUrl = String(input);
      capturedInit = init;
      return {
        ok: true,
        json: async () => ({
          contacts: [{ phone_last4: '4567', status: 'pending' }],
        }),
      } as unknown as Response;
    };

    const client = createRelayClient({
      fetch: fakeFetch,
      getConfig: fakeConfig,
      getInstallId: fakeInstallId,
    });

    const contacts: RegisterContact[] = [{ name: 'Mum', phone: '+201001234567' }];
    const res = await client.register('Driver', contacts);

    expect(res).toEqual({
      contacts: [{ phone_last4: '4567', status: 'pending' }],
    });
    expect(capturedUrl).toBe('https://relay.example.com/v1/register');
    expect(capturedInit?.method).toBe('POST');
    const headers = capturedInit?.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer test-api-key');
    expect(headers['X-Install-Id']).toBe('test-install-uuid-1234');
    expect(headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(String(capturedInit?.body))).toEqual({
      driver_name: 'Driver',
      contacts,
    });
  });

  it('sends proper headers and payload for sendSos', async () => {
    let capturedUrl = '';
    let capturedInit: RequestInit | undefined;

    const fakeFetch: typeof fetch = async (input, init) => {
      capturedUrl = String(input);
      capturedInit = init;
      return {
        ok: true,
        json: async () => ({
          ok: true,
          client_id: 'incident-uuid',
          results: [{ phone_last4: '4567', status: 'queued' }],
        }),
      } as unknown as Response;
    };

    const client = createRelayClient({
      fetch: fakeFetch,
      getConfig: fakeConfig,
      getInstallId: fakeInstallId,
    });

    const payload: SosRequestPayload = {
      client_id: 'incident-uuid',
      kind: 'crash',
      t_crash: 1795189202400,
      lat: 30.0444,
      lon: 31.2357,
    };
    const res = await client.sendSos(payload);

    expect(res).toEqual({
      ok: true,
      client_id: 'incident-uuid',
      results: [{ phone_last4: '4567', status: 'queued' }],
    });
    expect(capturedUrl).toBe('https://relay.example.com/v1/sos');
    const headers = capturedInit?.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer test-api-key');
    expect(headers['X-Install-Id']).toBe('test-install-uuid-1234');
  });

  it('queries sosStatus correctly', async () => {
    let capturedUrl = '';
    const fakeFetch: typeof fetch = async (input) => {
      capturedUrl = String(input);
      return {
        ok: true,
        json: async () => ({
          results: [{ phone_last4: '4567', status: 'delivered' }],
        }),
      } as unknown as Response;
    };

    const client = createRelayClient({
      fetch: fakeFetch,
      getConfig: fakeConfig,
      getInstallId: fakeInstallId,
    });

    const res = await client.sosStatus('incident-123');
    expect(capturedUrl).toBe('https://relay.example.com/v1/sos/incident-123');
    expect(res).toEqual({
      results: [{ phone_last4: '4567', status: 'delivered' }],
    });
  });

  it('unregisters successfully with DELETE /v1/register', async () => {
    let capturedMethod = '';
    const fakeFetch: typeof fetch = async (_input, init) => {
      capturedMethod = init?.method ?? '';
      return {
        ok: true,
        json: async () => ({ ok: true }),
      } as unknown as Response;
    };

    const client = createRelayClient({
      fetch: fakeFetch,
      getConfig: fakeConfig,
      getInstallId: fakeInstallId,
    });

    const res = await client.unregister();
    expect(capturedMethod).toBe('DELETE');
    expect(res).toEqual({ ok: true });
  });

  it('queries health without requiring auth headers', async () => {
    let capturedHeaders: Record<string, string> = {};
    const fakeFetch: typeof fetch = async (_input, init) => {
      capturedHeaders = (init?.headers ?? {}) as Record<string, string>;
      return {
        ok: true,
        json: async () => ({ whatsapp: 'connected', version: '1' }),
      } as unknown as Response;
    };

    const client = createRelayClient({
      fetch: fakeFetch,
      getConfig: fakeConfig,
      getInstallId: fakeInstallId,
    });

    const res = await client.health();
    expect(res).toEqual({ whatsapp: 'connected', version: '1' });
    expect(capturedHeaders['Authorization']).toBeUndefined();
    expect(capturedHeaders['X-Install-Id']).toBeUndefined();
  });

  it('handles 429 rate limit response by returning null', async () => {
    const fakeFetch: typeof fetch = async () =>
      ({
        ok: false,
        status: 429,
        statusText: 'Too Many Requests',
        json: async () => ({ error: 'rate limited' }),
      }) as unknown as Response;

    const client = createRelayClient({
      fetch: fakeFetch,
      getConfig: fakeConfig,
      getInstallId: fakeInstallId,
    });

    const res = await client.register('Driver', []);
    expect(res).toBeNull();
  });

  it('handles bad JSON or invalid response schema by returning null', async () => {
    const fakeFetchBadJson: typeof fetch = async () =>
      ({
        ok: true,
        json: async () => {
          throw new Error('invalid json');
        },
      }) as unknown as Response;

    const clientBadJson = createRelayClient({
      fetch: fakeFetchBadJson,
      getConfig: fakeConfig,
      getInstallId: fakeInstallId,
    });
    expect(await clientBadJson.register('Driver', [])).toBeNull();

    const fakeFetchInvalidSchema: typeof fetch = async () =>
      ({
        ok: true,
        json: async () => ({ unknown_field: 123 }),
      }) as unknown as Response;

    const clientInvalid = createRelayClient({
      fetch: fakeFetchInvalidSchema,
      getConfig: fakeConfig,
      getInstallId: fakeInstallId,
    });
    expect(await clientInvalid.sendSos({
      client_id: '1', kind: 'crash', t_crash: 100, lat: null, lon: null,
    })).toBeNull();
  });

  it('aborts when timeout is exceeded', async () => {
    const fakeFetch: typeof fetch = async (_input, init) => {
      return new Promise((resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new Error('aborted'));
        });
      });
    };

    const client = createRelayClient({
      fetch: fakeFetch,
      getConfig: fakeConfig,
      getInstallId: fakeInstallId,
      timeoutSosMs: 50,
      timeoutDefaultMs: 50,
    });

    const res = await client.sendSos({
      client_id: 'test',
      kind: 'crash',
      t_crash: 1000,
      lat: null,
      lon: null,
    });
    expect(res).toBeNull();
  });
});
