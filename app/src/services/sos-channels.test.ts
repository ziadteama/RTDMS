import type { Contact } from '@/state/secure';
import type { RelayClient } from './relay/client';
import type { SosGetResponse, SosPostResponse } from './relay/types';
import { startSosChannels, type TimerHandle } from './sos-channels';

describe('startSosChannels', () => {
  const contacts: Contact[] = [
    { id: '1', name: 'Mum', phone: '+201001234567' },
    { id: '2', name: 'Dad', phone: '+201007654321' },
  ];

  type TimeoutCallback = () => void;
  function createFakeClock() {
    let currentTime = 1000;
    const timers = new Map<number, { at: number; cb: TimeoutCallback; interval?: number }>();
    let nextId = 1;

    return {
      now: () => currentTime,
      setTimeout: (cb: TimeoutCallback, delay: number) => {
        const id = nextId++;
        timers.set(id, { at: currentTime + delay, cb });
        return id as unknown as TimerHandle;
      },
      clearTimeout: (id: TimerHandle) => {
        timers.delete(Number(id));
      },
      setInterval: (cb: TimeoutCallback, interval: number) => {
        const id = nextId++;
        timers.set(id, { at: currentTime + interval, cb, interval });
        return id as unknown as TimerHandle;
      },
      clearInterval: (id: TimerHandle) => {
        timers.delete(Number(id));
      },
      advanceTimersByTime: async (ms: number) => {
        const target = currentTime + ms;
        while (true) {
          let earliestId: number | null = null;
          let earliestTime = Infinity;
          for (const [id, t] of timers.entries()) {
            if (t.at <= target && t.at < earliestTime) {
              earliestTime = t.at;
              earliestId = id;
            }
          }
          if (earliestId === null) {
            currentTime = target;
            break;
          }
          currentTime = earliestTime;
          const timer = timers.get(earliestId);
          if (timer) {
            if (timer.interval) {
              timer.at = currentTime + timer.interval;
            } else {
              timers.delete(earliestId);
            }
            timer.cb();
            // flush microtasks
            await Promise.resolve();
          }
        }
      },
    };
  }

  it('runs relay and SMS in parallel; relay failure does not block SMS', async () => {
    let smsSent = false;
    let relayAttempted = false;

    const fakeRelay: RelayClient = {
      register: async () => null,
      sendSos: async () => {
        relayAttempted = true;
        return null; // Relay fails
      },
      sosStatus: async () => null,
      unregister: async () => null,
      health: async () => null,
    };

    const progressSnapshots: unknown[] = [];
    const fakeSendSms = async (numbers: string[]) => {
      smsSent = true;
      return numbers.length;
    };

    const handle = startSosChannels(
      {
        incidentId: 1,
        clientId: 'client-1',
        kind: 'crash',
        at: 1000,
        lat: 30.0,
        lon: 31.0,
        contacts,
        onProgress: (p) => progressSnapshots.push(JSON.parse(JSON.stringify(p))),
      },
      {
        relayClient: fakeRelay,
        sendSms: fakeSendSms,
      },
    );

    await Promise.resolve();
    await Promise.resolve();

    expect(relayAttempted).toBe(true);
    expect(smsSent).toBe(true);
    handle.stop();
  });

  it('never marks delivered unless reported, and retries SMS after 60s without report', async () => {
    const clock = createFakeClock();
    let smsCalls = 0;
    const sentNumbers: string[][] = [];

    const fakeSendSms = async (numbers: string[]) => {
      smsCalls++;
      sentNumbers.push([...numbers]);
      return numbers.length;
    };

    let triggerSmsStatus: ((e: { phone: string; status: 'sent' | 'delivered' | 'failed' }) => void) | null = null;
    const onSmsStatusSub = (handler: (e: { phone: string; status: 'sent' | 'delivered' | 'failed' }) => void) => {
      triggerSmsStatus = handler;
      return () => {
        triggerSmsStatus = null;
      };
    };

    const fakeRelay: RelayClient = {
      register: async () => null,
      sendSos: async (): Promise<SosPostResponse> => ({
        ok: true,
        client_id: 'client-1',
        results: [
          { phone_last4: '4567', status: 'queued' },
          { phone_last4: '4321', status: 'queued' },
        ],
      }),
      sosStatus: async (): Promise<SosGetResponse> => ({
        results: [
          { phone_last4: '4567', status: 'sent' },
          { phone_last4: '4321', status: 'sent' },
        ],
      }),
      unregister: async () => null,
      health: async () => null,
    };

    let latestProgress: { contacts: { phone: string; sms: string; whatsapp: string }[] } | null = null;

    const handle = startSosChannels(
      {
        incidentId: 1,
        clientId: 'client-1',
        kind: 'crash',
        at: 1000,
        lat: 30.0,
        lon: 31.0,
        contacts,
        onProgress: (p) => {
          latestProgress = p;
        },
      },
      {
        relayClient: fakeRelay,
        sendSms: fakeSendSms,
        onSmsStatusSub,
        clock,
      },
    );

    // Initial send
    await Promise.resolve();
    await Promise.resolve();

    expect(smsCalls).toBe(1);
    expect(sentNumbers[0]).toEqual(['+201001234567', '+201007654321']);
    // Contact SMS must be 'sent', NEVER 'delivered' yet
    expect(latestProgress!.contacts[0]!.sms).toBe('sent');
    expect(latestProgress!.contacts[1]!.sms).toBe('sent');

    // Simulate delivery report arriving ONLY for contact 0 (Mum)
    triggerSmsStatus!({ phone: '+201001234567', status: 'delivered' });
    expect(latestProgress!.contacts[0]!.sms).toBe('delivered');
    expect(latestProgress!.contacts[1]!.sms).toBe('sent');

    // Advance clock by 60 s -> retry should happen ONLY for contact 1 (Dad)
    await clock.advanceTimersByTime(60_000);

    expect(smsCalls).toBe(2);
    expect(sentNumbers[1]).toEqual(['+201007654321']);

    handle.stop();
  });

  it('polls GET /v1/sos/{client_id} every 5s to update WhatsApp status', async () => {
    const clock = createFakeClock();
    let pollCount = 0;

    const fakeRelay: RelayClient = {
      register: async () => null,
      sendSos: async (): Promise<SosPostResponse> => ({
        ok: true,
        client_id: 'c-1',
        results: [{ phone_last4: '4567', status: 'queued' }],
      }),
      sosStatus: async (): Promise<SosGetResponse> => {
        pollCount++;
        const status = pollCount >= 2 ? 'delivered' : 'sent';
        return {
          results: [{ phone_last4: '4567', status }],
        };
      },
      unregister: async () => null,
      health: async () => null,
    };

    let latestProgress: { contacts: { whatsapp: string }[] } | null = null;

    const handle = startSosChannels(
      {
        incidentId: 1,
        clientId: 'c-1',
        kind: 'crash',
        at: 1000,
        lat: 30.0,
        lon: 31.0,
        contacts: [contacts[0]!],
        onProgress: (p) => {
          latestProgress = p;
        },
      },
      {
        relayClient: fakeRelay,
        sendSms: async () => 1,
        clock,
      },
    );

    await Promise.resolve();
    await Promise.resolve();
    expect(latestProgress!.contacts[0]!.whatsapp).toBe('queued');

    // Advance 5 s: first poll -> status 'sent'
    await clock.advanceTimersByTime(5_000);
    expect(pollCount).toBe(1);
    expect(latestProgress!.contacts[0]!.whatsapp).toBe('sent');

    // Advance another 5 s: second poll -> status 'delivered'
    await clock.advanceTimersByTime(5_000);
    expect(pollCount).toBe(2);
    expect(latestProgress!.contacts[0]!.whatsapp).toBe('delivered');

    handle.stop();
  });
});
