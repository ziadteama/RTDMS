/**
 * Types for the SOS relay client, strictly matching contracts/sos-relay/CONTRACT.md.
 * One source of truth for the app; no copies elsewhere.
 */

export type ContactRegisterStatus = 'pending' | 'ok' | 'opted_out' | 'invalid' | 'failed';

export type RegisterContact = {
  name: string;
  phone: string;
};

export type RegisterPayload = {
  driver_name: string;
  contacts: RegisterContact[];
};

export type RegisterResponseContact = {
  phone_last4: string;
  status: ContactRegisterStatus;
};

export type RegisterResponse = {
  contacts: RegisterResponseContact[];
};

export type SosRequestPayload = {
  client_id: string;
  kind: 'crash' | 'manual';
  t_crash: number;
  lat: number | null;
  lon: number | null;
};

export type SosStatus = 'queued' | 'sent' | 'delivered' | 'read' | 'failed' | 'opted_out';

export type SosResultContact = {
  phone_last4: string;
  status: SosStatus;
};

export type SosPostResponse = {
  ok: boolean;
  client_id: string;
  results: { phone_last4: string; status: 'queued' }[];
};

export type SosGetResponse = {
  results: SosResultContact[];
};

export type DeleteRegisterResponse = {
  ok: boolean;
};

export type HealthResponse = {
  whatsapp: 'connected' | 'disconnected' | 'pairing';
  version: string;
};

export type ChannelStatus =
  | 'queued'
  | 'sent'
  | 'delivered'
  | 'read'
  | 'failed'
  | 'opted_out'
  | 'unknown';
