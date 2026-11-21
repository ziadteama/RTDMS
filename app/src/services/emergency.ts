/**
 * Crash / SOS flow: log the incident, ask the Pi to save its clip, open the countdown, and when it
 * runs out send SMS with a Google Maps link to every contact, then call the configured number or first contact.
 * Android sends and calls without a tap (sahi-native); elsewhere it falls back to the composer.
 */
import * as Location from 'expo-location';
import { router } from 'expo-router';
import { Linking, Platform } from 'react-native';

import SahiNative from '@modules/sahi-native';
import { t } from '@/i18n';
import type { CrashEvent, MotionSample } from '@/crash/detector';
import { magnitudeG } from '@/crash/detector';
import { db } from '@/state/db';
import { useLive } from '@/state/live';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';

import { speak } from './alerts';
import { incidentClientId, incidentQueue } from './incident-delivery';
import { startSosChannels, type ContactChannelState } from './sos-channels';
import { currentTripId } from './trips';

export const SOS_NOTIFICATION_ID = 2001;
export const STAGE_TWO_DELAY_MS = 15_000;

/** ~20 Hz |a| in g, enough to draw the impact. */
function downsample(motion: MotionSample[]): [number, number][] {
  const out: [number, number][] = [];
  let next = -Infinity;
  for (const s of motion)
    if (s.t >= next) {
      out.push([Math.round(s.t), Math.round(magnitudeG(s) * 100) / 100]);
      next = s.t + 50;
    }
  // keep the true peak
  const peak = motion.reduce<MotionSample | null>((a, s) => (!a || magnitudeG(s) > magnitudeG(a) ? s : a), null);
  if (peak) out.push([Math.round(peak.t), Math.round(magnitudeG(peak) * 100) / 100]);
  return out.sort((a, b) => a[0] - b[0]);
}

export function triggerSos(kind: 'crash' | 'manual', e?: CrashEvent, motion: MotionSample[] = []): number {
  const live = useLive.getState();
  const tripId = currentTripId();
  const at = e?.tImpact ?? Date.now();
  const id = db.addIncident({
    tripId,
    t: at,
    kind,
    gPeak: e?.gPeak ?? null,
    lat: live.location?.lat ?? null,
    lon: live.location?.lon ?? null,
    piId: null,
    outcome: 'pending',
    checks: e?.checks ?? null,
    motion: downsample(motion),
    clipPath: null,
    smsSent: 0,
    called: null,
  });
  if (tripId !== null)
    db.addEvent(tripId, at, kind === 'crash' ? 'crash' : 'sos', String(id), e ? String(e.gPeak) : null);

  // Persist before delivery; the Pi link never blocks the countdown, SMS or call.
  void incidentQueue.enqueue({ client_id: incidentClientId(), localId: id,
    t_crash: at, g_peak: e?.gPeak ?? 0, lat: live.location?.lat ?? null,
    lon: live.location?.lon ?? null }).then(() => incidentQueue.flush()).catch(() => {});

  if (kind === 'crash' && SahiNative)
    SahiNative.notify(SOS_NOTIFICATION_ID, 'sos', t('sos.notifTitle'), t('sos.notifBody'), `sahi://sos?incident=${id}`);
  router.push({ pathname: '/sos', params: { incident: String(id) } });
  return id;
}

export function cancelSos(id: number): void {
  db.saveIncident(id, { outcome: 'cancelled' });
  SahiNative?.cancel(SOS_NOTIFICATION_ID);
}

async function bestLocation(): Promise<{ lat: number; lon: number } | null> {
  const known = useLive.getState().location;
  if (known && Date.now() - known.at < 60_000) return known;
  try {
    const p = await Promise.race([
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
      new Promise<null>((r) => setTimeout(() => r(null), 5000)),
    ]);
    if (p) return { lat: p.coords.latitude, lon: p.coords.longitude };
  } catch {
    // fall through to the last known fix
  }
  return known;
}

export type CallProgressState = 'none' | 'waiting' | 'starting' | 'calling' | 'failed';

export type SosProgressInfo = {
  sent?: number;
  number?: string;
  callState?: CallProgressState;
  contacts?: ContactChannelState[];
  /** Demo mode: nothing real was sent or dialed. */
  demo?: boolean;
};

export type SosProgress = (step: 'sms' | 'waiting' | 'call' | 'done', info: SosProgressInfo) => void;

/** Countdown expired (or "Send now"): parallel WhatsApp relay + link-free SMS, then the call. */
export async function runEmergency(id: number, onProgress: SosProgress): Promise<void> {
  const { contacts } = useSecure.getState();
  const { callTarget, emergencyNumber } = useSettings.getState();
  const incident = db.getIncident(id);
  if (incident?.outcome === 'cancelled') return;
  if (useSettings.getState().demo) {
    // Demo never sends real messages or places real calls, and never fabricates results.
    onProgress('done', { demo: true });
    return;
  }
  const kind = incident?.kind ?? 'manual';
  const loc = await bestLocation();
  if (db.getIncident(id)?.outcome === 'cancelled') return;
  if (loc) db.saveIncident(id, { lat: loc.lat, lon: loc.lon });

  const clientId = incidentClientId();
  const at = incident?.t ?? Date.now();
  let latestSent = 0;
  let latestContacts: ContactChannelState[] = [];

  const channels = startSosChannels({
    incidentId: id,
    clientId,
    kind,
    at,
    lat: loc?.lat ?? null,
    lon: loc?.lon ?? null,
    contacts,
    onProgress: (p) => {
      latestSent = p.smsSentCount;
      latestContacts = p.contacts;
      db.saveIncident(id, { smsSent: latestSent });
      onProgress('sms', { sent: latestSent, contacts: latestContacts });
    },
  });

  const numbers = contacts.map((c) => c.phone);
  const number = callTarget === 'contact' && numbers[0] ? numbers[0] : emergencyNumber;
  onProgress('waiting', { number, callState: 'waiting', sent: latestSent, contacts: latestContacts });

  await new Promise<void>((resolve) => setTimeout(resolve, STAGE_TWO_DELAY_MS));
  if (db.getIncident(id)?.outcome === 'cancelled') {
    channels.stop();
    return;
  }

  // Real state: "starting" before dial returns, then "calling" or "failed"
  onProgress('call', { number, callState: 'starting', sent: latestSent, contacts: latestContacts });
  const called = await dial(number);
  const callState: CallProgressState = called ? 'calling' : 'failed';
  db.saveIncident(id, { called: number, outcome: latestSent > 0 || called ? 'sent' : 'failed' });
  SahiNative?.cancel(SOS_NOTIFICATION_ID);
  onProgress('done', { sent: latestSent, number, callState, contacts: latestContacts });
}

export function announceCountdown(seconds: number): void {
  speak('voice.sos', { s: seconds });
}

async function dial(number: string): Promise<boolean> {
  let called = false;
  if (SahiNative && Platform.OS === 'android') {
    try {
      await SahiNative.call(number);
      called = true;
    } catch {
      called = false;
    }
  }
  if (!called) await Linking.openURL(`tel:${number}`).catch(() => {});
  return called;
}
