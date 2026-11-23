/**
 * Phone sensors during a trip: GPS (speed, location) and accelerometer + gyroscope → crash
 * detector. On Android, expo-location's foreground service (with its notification) keeps the app
 * process alive with the screen off; the sahi-native motion listener keeps sampling there (unlike
 * expo-sensors, which pauses in the background).
 */
import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';
import { Platform } from 'react-native';

import SahiNative from '@modules/sahi-native';
import { armState, gpsLost } from '@/crash/arm-state';
import { CrashMonitor, synthesizeCrash, unpackMotion, type CrashExtras } from '@/crash/detector';
import { speedAt } from '@/demo/scenario';
import { t } from '@/i18n';
import { DemoTransport } from '@/pi/transport';
import { payloadTime } from '@/pi/time';
import { setLive, useLive } from '@/state/live';
import { useSettings } from '@/state/settings';

import { triggerSos } from './emergency';
import { pi } from './pi';
import { startUnresponsiveMonitor } from './unresponsive';
import { startWatchAckCancel } from './watch-ack-cancel';

export { gpsLost };

export const LOCATION_TASK = 'sahi-location';
export const MOTION_HZ = 100;
let motionAt: number | null = null;

const crash = new CrashMonitor();
const faceLost: number[] = [];
const hr: { t: number; bpm: number }[] = [];
const recentSpeeds: { t: number; kmh: number }[] = [];

function onFix(loc: Location.LocationObject): void {
  const kmh = loc.coords.speed != null && loc.coords.speed >= 0 ? loc.coords.speed * 3.6 : null;
  if (useSettings.getState().demo) {
    setLive({ location: { lat: loc.coords.latitude, lon: loc.coords.longitude, at: loc.timestamp } });
    return; // demo speed comes from the scenario
  }
  recordSpeed(loc.timestamp, kmh);
  setLive({
    speedKmh: kmh,
    gpsAt: loc.timestamp,
    location: { lat: loc.coords.latitude, lon: loc.coords.longitude, at: loc.timestamp },
  });
}

function recordSpeed(at: number, kmh: number | null): void {
  crash.addSpeed({ t: at, kmh });
  if (kmh !== null) recentSpeeds.push({ t: at, kmh });
  while (recentSpeeds.length && recentSpeeds[0]!.t < at - 10_000) recentSpeeds.shift();
}

// Background location updates arrive here, also with the screen off (registered at import time,
// as TaskManager requires).
if (Platform.OS !== 'web')
  TaskManager.defineTask<{ locations: Location.LocationObject[] }>(LOCATION_TASK, async ({ data, error }) => {
    if (error || !data) return;
    for (const l of data.locations) onFix(l);
  });

function isArmed() {
  const { crashDetection, paused } = useSettings.getState();
  return armState({ enabled: crashDetection, paused, now: Date.now(),
    gpsAt: useLive.getState().gpsAt, motionAt, speeds: recentSpeeds });
}

function extras(): CrashExtras {
  const physioOn = useLive.getState().physioSupported === true;
  return { faceLost: [...faceLost], hr: physioOn ? [...hr] : undefined };
}

function check(): void {
  const now = Date.now();
  const { armed, reason } = isArmed();
  setLive({ armed, armReason: reason });
  // Let in-flight impacts finish confirmation even after speed falls below the arming floor.
  if (!useSettings.getState().crashDetection || useSettings.getState().paused) return;
  const e = crash.check(now, extras());
  if (e) triggerSos('crash', e, crash.window(e.tImpact - 3000, e.tImpact + 5000));
}

/** Demo mode / drop test: run a synthetic crash through the real detector. */
export function simulateCrash(): void {
  const now = Date.now();
  const c = synthesizeCrash(now - 13_000, 6.5, Math.max(45, useLive.getState().speedKmh ?? 0));
  for (const s of c.speeds) recordSpeed(s.t, s.kmh);
  crash.addMotion(c.samples);
  const e = crash.check(now, extras());
  if (e) triggerSos('crash', e, crash.window(e.tImpact - 3000, e.tImpact + 5000));
}

export async function locationPermission(): Promise<boolean> {
  const fg = await Location.getForegroundPermissionsAsync();
  return fg.granted;
}

export function startMonitor(): () => void {
  const stopUnresponsive = startUnresponsiveMonitor();
  const stopWatchAck = startWatchAckCancel();
  const demo = useSettings.getState().demo;
  let stopped = false;
  let watch: Location.LocationSubscription | null = null;
  const timers: ReturnType<typeof setInterval>[] = [];
  crash.reset();
  recentSpeeds.length = 0;
  motionAt = null;

  // Pi-side optional evidence, kept for the last minute.
  const unsub = useLive.subscribe((s, prev) => {
    const now = Date.now();
    if (s.status !== prev.status && s.status && !s.status.face) faceLost.push(now);
    if (s.physio !== prev.physio && s.physio?.hr_bpm != null) hr.push({ t: payloadTime(s.physio, now), bpm: s.physio.hr_bpm });
    while (faceLost.length && faceLost[0]! < now - 60_000) faceLost.shift();
    while (hr.length && hr[0]!.t < now - 60_000) hr.shift();
  });

  void (async () => {
    if (!(await locationPermission())) {
      setLive({ gpsAt: null, speedKmh: null });
    } else if (Platform.OS === 'android') {
      await Location.startLocationUpdatesAsync(LOCATION_TASK, {
        accuracy: Location.Accuracy.BestForNavigation,
        timeInterval: 1000,
        distanceInterval: 0,
        foregroundService: {
          notificationTitle: t('service.title'),
          notificationBody: t('service.body'),
          killServiceOnDestroy: false,
        },
      }).catch(() => setLive({ gpsAt: null }));
    } else {
      watch = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.BestForNavigation, timeInterval: 1000, distanceInterval: 0 },
        onFix,
      ).catch(() => null);
    }
    if (stopped) watch?.remove();
  })();

  const motion = SahiNative?.addListener('onMotion', (e) => {
    const batch = unpackMotion(e.samples);
    if (batch.length) motionAt = batch[batch.length - 1]!.t;
    crash.addMotion(batch);
  });
  SahiNative?.startMotion(MOTION_HZ);

  if (demo) {
    // Demo GPS: the scenario's speed profile (lets examiners see the driving lock and arming).
    timers.push(
      setInterval(() => {
        const transport = pi();
        const kmh = transport instanceof DemoTransport ? speedAt(transport.now()) : 0;
        motionAt = Date.now();
        recordSpeed(Date.now(), kmh);
        setLive({ speedKmh: kmh, gpsAt: Date.now() });
      }, 1000),
    );
  }
  timers.push(setInterval(check, 500));

  return () => {
    stopped = true;
    stopUnresponsive();
    stopWatchAck();
    unsub();
    timers.forEach(clearInterval);
    motion?.remove();
    SahiNative?.stopMotion();
    watch?.remove();
    if (Platform.OS === 'android')
      void Location.hasStartedLocationUpdatesAsync(LOCATION_TASK)
        .then((on) => (on ? Location.stopLocationUpdatesAsync(LOCATION_TASK) : undefined))
        .catch(() => {});
    setLive({ armed: false, armReason: 'disabled', speedKmh: null, gpsAt: null });
  };
}

