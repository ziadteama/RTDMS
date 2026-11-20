/**
 * Crash / SOS flow: log the incident, ask the Pi to save its clip, open the countdown, and when it
 * runs out send SMS with a Google Maps link to every contact, then call 123 or the first contact.
 * Android sends and calls without a tap (sahi-native); elsewhere it falls back to the composer.
 */
import * as Location from 'expo-location';
import { router } from 'expo-router';
import { Linking, Platform } from 'react-native';

import SahiNative from '@modules/sahi-native';
import { t } from '@/i18n';
import type { CrashEvent, MotionSample } from '@/crash/detector';
import { magnitudeG } from '@/crash/detector';
import type { IncidentRequest } from '@/pi/types';
import { db } from '@/state/db';
import { useLive } from '@/state/live';
import { useSecure } from '@/state/secure';
import { useSettings } from '@/state/settings';

import { speak } from './alerts';
import { pi } from './pi';
import { currentTripId } from './trips';

export const SOS_NOTIFICATION_ID = 2001;
export const COUNTDOWN_S = { crash: 30, manual: 10 } as const;

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

  // Ask the Pi to keep its ring buffer (15 s before + 10 s after). Best effort: help comes first.
  if (live.connection === 'online') {
    const body: IncidentRequest = { t_crash: at, g_peak: e?.gPeak ?? 0, lat: live.location?.lat ?? null, lon: live.location?.lon ?? null };
    pi()
      .send('POST', '/incident', body)
      .then((r) => {
        const piId = (r as { id?: unknown }).id;
        if (typeof piId === 'string') db.saveIncident(id, { piId });
      })
      .catch(() => {});
  }

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

export type SosProgress = (step: 'sms' | 'call' | 'done', info: { sent?: number; number?: string }) => void;

/** Countdown expired (or "Send now"): SMS to all contacts, then the call. */
export async function runEmergency(id: number, onProgress: SosProgress): Promise<void> {
  const { contacts } = useSecure.getState();
  const { callTarget, ambulanceNumber } = useSettings.getState();
  const loc = await bestLocation();
  const time = new Date().toLocaleTimeString();
  const text = loc
    ? t('sos.message', { link: `https://maps.google.com/?q=${loc.lat.toFixed(6)},${loc.lon.toFixed(6)}`, time })
    : t('sos.messageNoLoc', { time });
  if (loc) db.saveIncident(id, { lat: loc.lat, lon: loc.lon });

  let sent = 0;
  const numbers = contacts.map((c) => c.phone);
  onProgress('sms', {});
  if (numbers.length) {
    if (SahiNative && Platform.OS === 'android') {
      try {
        sent = await SahiNative.sendSms(numbers, text);
      } catch {
        sent = 0;
      }
    } else {
      // iOS / web cannot send silently: open the composer (needs a tap).
      await Linking.openURL(`sms:${numbers.join(',')}${Platform.OS === 'ios' ? '&' : '?'}body=${encodeURIComponent(text)}`).catch(() => {});
    }
  }
  db.saveIncident(id, { smsSent: sent });
  onProgress('sms', { sent });

  const number = callTarget === 'contact' && numbers[0] ? numbers[0] : ambulanceNumber;
  onProgress('call', { number });
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
  db.saveIncident(id, { called: number, outcome: sent > 0 || called ? 'sent' : 'failed' });
  SahiNative?.cancel(SOS_NOTIFICATION_ID);
  onProgress('done', { sent, number });
}

export function announceCountdown(seconds: number): void {
  speak('voice.sos', { s: seconds });
}
