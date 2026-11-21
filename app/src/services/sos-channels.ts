import { Linking, Platform } from 'react-native';
import SahiNative from '@modules/sahi-native';
import type { Contact } from '@/state/secure';
import { useSettings } from '@/state/settings';
import { fakeRelayClient } from './relay/fake-client';
import { relay, type RelayClient } from './relay/client';
import type { ChannelStatus, SosRequestPayload } from './relay/types';
import { buildSosSms, type SosMessageKind } from './sos-message';

export type ContactChannelState = {
  id: string;
  name: string;
  phone: string;
  phoneLast4: string;
  whatsapp: ChannelStatus;
  sms: ChannelStatus;
};

export type SosChannelProgress = {
  contacts: ContactChannelState[];
  smsSentCount: number;
};

export type TimerHandle = ReturnType<typeof globalThis.setTimeout>;

export type SosChannelsDeps = {
  relayClient?: RelayClient;
  sendSms?: (numbers: string[], text: string) => Promise<number>;
  onSmsStatusSub?: (handler: (e: { phone: string; status: 'sent' | 'delivered' | 'failed' }) => void) => () => void;
  clock?: {
    now: () => number;
    setTimeout: (cb: () => void, ms: number) => TimerHandle;
    clearTimeout: (id: TimerHandle) => void;
    setInterval: (cb: () => void, ms: number) => TimerHandle;
    clearInterval: (id: TimerHandle) => void;
  };
};

export const SMS_RETRY_DELAY_MS = 60_000;
export const RELAY_POLL_INTERVAL_MS = 5_000;
export const RELAY_POLL_MAX_MS = 180_000;

function defaultSmsStatusSub(handler: (e: { phone: string; status: 'sent' | 'delivered' | 'failed' }) => void): () => void {
  if (!SahiNative || typeof (SahiNative as unknown as { addListener?: unknown }).addListener !== 'function') {
    return () => {};
  }
  const sub = SahiNative.addListener('onSmsStatus', handler);
  return () => {
    sub.remove();
  };
}

export function startSosChannels(
  params: {
    incidentId: number;
    clientId: string;
    kind: SosMessageKind;
    at: number;
    lat: number | null;
    lon: number | null;
    contacts: Contact[];
    onProgress: (status: SosChannelProgress) => void;
  },
  deps: SosChannelsDeps = {},
): { stop: () => void } {
  const clock = deps.clock ?? {
    now: Date.now,
    setTimeout: globalThis.setTimeout,
    clearTimeout: globalThis.clearTimeout,
    setInterval: globalThis.setInterval,
    clearInterval: globalThis.clearInterval,
  };
  const isDemo = useSettings.getState().demo;
  const relayClient = deps.relayClient ?? (isDemo ? fakeRelayClient : relay);
  const smsSender = deps.sendSms ?? (async (numbers, text) => {
    if (SahiNative && Platform.OS === 'android') {
      try {
        return await SahiNative.sendSms(numbers, text);
      } catch {
        return 0;
      }
    }
    if (numbers.length) {
      await Linking.openURL(`sms:${numbers.join(',')}${Platform.OS === 'ios' ? '&' : '?'}body=${encodeURIComponent(text)}`).catch(() => {});
      return numbers.length;
    }
    return 0;
  });
  const smsSub = deps.onSmsStatusSub ?? defaultSmsStatusSub;

  const contactsState: ContactChannelState[] = params.contacts.map((c) => ({
    id: c.id,
    name: c.name,
    phone: c.phone,
    phoneLast4: c.phone.replace(/\D/g, '').slice(-4),
    whatsapp: 'queued',
    sms: 'queued',
  }));

  let stopped = false;
  let pollInterval: TimerHandle | null = null;
  let retryTimer: TimerHandle | null = null;
  let maxPollTimer: TimerHandle | null = null;

  const notify = () => {
    if (stopped) return;
    const sentCount = contactsState.filter((c) => c.sms === 'sent' || c.sms === 'delivered' || c.sms === 'read').length;
    params.onProgress({
      contacts: contactsState.map((c) => ({ ...c })),
      smsSentCount: sentCount,
    });
  };

  const updateWhatsapp = (phoneLast4: string, status: ChannelStatus) => {
    const contact = contactsState.find((c) => c.phoneLast4 === phoneLast4);
    if (contact) {
      contact.whatsapp = status;
    }
  };

  const updateSms = (phone: string, status: 'sent' | 'delivered' | 'failed') => {
    const normPhone = phone.replace(/\D/g, '');
    const contact = contactsState.find((c) => c.phone.replace(/\D/g, '').endsWith(normPhone.slice(-7)) || c.phone === phone);
    if (contact) {
      contact.sms = status;
      notify();
    }
  };

  const unsubscribeSms = smsSub((e) => updateSms(e.phone, e.status));

  const text = buildSosSms({
    kind: params.kind,
    date: new Date(params.at),
    lat: params.lat,
    lon: params.lon,
  });

  const numbers = contactsState.map((c) => c.phone);

  // Parallel Task (a): Relay POST /v1/sos
  const relayTask = async () => {
    const payload: SosRequestPayload = {
      client_id: params.clientId,
      kind: params.kind,
      t_crash: params.at,
      lat: params.lat,
      lon: params.lon,
    };
    try {
      const res = await relayClient.sendSos(payload);
      if (res?.ok && Array.isArray(res.results)) {
        for (const item of res.results) {
          updateWhatsapp(item.phone_last4, item.status);
        }
      } else {
        for (const c of contactsState) c.whatsapp = 'failed';
      }
    } catch {
      for (const c of contactsState) c.whatsapp = 'failed';
    }
    notify();
  };

  // Parallel Task (b): Link-free SMS
  const smsTask = async (recipientNumbers: string[]) => {
    if (!recipientNumbers.length) return;
    try {
      const sent = await smsSender(recipientNumbers, text);
      for (const c of contactsState) {
        if (recipientNumbers.includes(c.phone)) {
          // Never mark delivered on send; only sent or failed
          if (c.sms !== 'delivered') {
            c.sms = sent > 0 ? 'sent' : 'failed';
          }
        }
      }
    } catch {
      for (const c of contactsState) {
        if (recipientNumbers.includes(c.phone) && c.sms !== 'delivered') {
          c.sms = 'failed';
        }
      }
    }
    notify();
  };

  notify();
  void relayTask();
  void smsTask(numbers);

  // Poll GET /v1/sos/{client_id} every 5 s
  pollInterval = clock.setInterval(async () => {
    if (stopped) return;
    try {
      const res = await relayClient.sosStatus(params.clientId);
      if (res?.results) {
        for (const item of res.results) {
          updateWhatsapp(item.phone_last4, item.status);
        }
        notify();
      }
    } catch {
      // keep polling until timeout
    }
  }, RELAY_POLL_INTERVAL_MS);

  // SMS retry after ~60 s without delivery report
  retryTimer = clock.setTimeout(() => {
    if (stopped) return;
    const undelivered = contactsState.filter((c) => c.sms !== 'delivered').map((c) => c.phone);
    if (undelivered.length) {
      void smsTask(undelivered);
    }
  }, SMS_RETRY_DELAY_MS);

  // Stop polling after 3 minutes
  maxPollTimer = clock.setTimeout(() => {
    if (pollInterval) clock.clearInterval(pollInterval);
    pollInterval = null;
  }, RELAY_POLL_MAX_MS);

  return {
    stop: () => {
      stopped = true;
      if (pollInterval) clock.clearInterval(pollInterval);
      if (retryTimer) clock.clearTimeout(retryTimer);
      if (maxPollTimer) clock.clearTimeout(maxPollTimer);
      unsubscribeSms();
    },
  };
}
