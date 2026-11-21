import type { Contact } from '@/state/secure';
import type { RelayClient } from './client';
import { syncRelayContacts } from './contacts';
import type { RegisterResponse } from './types';

describe('syncRelayContacts & registration status mapping', () => {
  const sampleContacts: Contact[] = [
    { id: '1', name: 'Mum', phone: '01001234567' },
    { id: '2', name: 'Dad', phone: '01009876543' },
    { id: '3', name: 'Work', phone: '01005551111' },
    { id: '4', name: 'Friend', phone: '01002223333' },
  ];

  it('normalizes numbers to E.164 and maps relay statuses correctly', async () => {
    let capturedDriver = '';
    let capturedList: { name: string; phone: string }[] = [];

    const fakeRelay: RelayClient = {
      register: async (driverName, contacts): Promise<RegisterResponse> => {
        capturedDriver = driverName;
        capturedList = contacts;
        return {
          contacts: [
            { phone_last4: '4567', status: 'ok' },
            { phone_last4: '6543', status: 'opted_out' },
            { phone_last4: '1111', status: 'invalid' },
            { phone_last4: '3333', status: 'pending' },
          ],
        };
      },
      sendSos: async () => null,
      sosStatus: async () => null,
      unregister: async () => null,
      health: async () => null,
    };

    const result = await syncRelayContacts('Driver', sampleContacts, fakeRelay);

    expect(capturedDriver).toBe('Driver');
    expect(capturedList).toEqual([
      { name: 'Mum', phone: '+201001234567' },
      { name: 'Dad', phone: '+201009876543' },
      { name: 'Work', phone: '+201005551111' },
      { name: 'Friend', phone: '+201002223333' },
    ]);

    expect(result[0]!.relayStatus).toBe('ok');
    expect(result[1]!.relayStatus).toBe('opted_out');
    expect(result[2]!.relayStatus).toBe('invalid');
    expect(result[3]!.relayStatus).toBe('pending');
  });

  it('marks contacts as failed when relay call fails, but keeps contacts saved', async () => {
    const failingRelay: RelayClient = {
      register: async () => null, // network/server failure
      sendSos: async () => null,
      sosStatus: async () => null,
      unregister: async () => null,
      health: async () => null,
    };

    const result = await syncRelayContacts('Driver', sampleContacts, failingRelay);

    expect(result).toHaveLength(4);
    for (const c of result) {
      expect(c.relayStatus).toBe('failed');
      expect(c.phone.startsWith('+20')).toBe(true);
    }
  });

  it('calls unregister when contacts list is empty', async () => {
    let unregisterCalled = false;
    const fakeRelay: RelayClient = {
      register: async () => null,
      sendSos: async () => null,
      sosStatus: async () => null,
      unregister: async () => {
        unregisterCalled = true;
        return { ok: true };
      },
      health: async () => null,
    };

    const result = await syncRelayContacts('Driver', [], fakeRelay);
    expect(unregisterCalled).toBe(true);
    expect(result).toEqual([]);
  });
});
