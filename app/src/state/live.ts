import { create } from 'zustand';

import type { ArmReason } from '@/crash/arm-state';
import type { PiAlert, PiPhysio, PiStatus } from '@/pi/types';

export type Connection = 'connecting' | 'online' | 'offline';

/**
 * Live data from the Pi + phone sensors. Written by services at 5 Hz; screens subscribe with
 * narrow selectors so a poll only re-renders what changed.
 */
export type LiveState = {
  connection: Connection;
  /** Which link feeds the data right now: Bluetooth or the HTTP fallback; null until known. */
  link: 'ble' | 'http' | null;
  /** The phone's Bluetooth is switched off, so the unit cannot be reached over Bluetooth. */
  btOff: boolean;
  lastOkAt: number | null;
  status: PiStatus | null;
  alert: PiAlert | null;
  /** null = not known yet, false = this Pi has no /alert (older stream.py). */
  alertSupported: boolean | null;
  calibrating: boolean;
  physio: PiPhysio | null;
  physioSupported: boolean | null;
  /** GPS speed (km/h), null when there is no fix with speed. */
  speedKmh: number | null;
  gpsAt: number | null;
  location: { lat: number; lon: number; at: number } | null;
  /** Phone-only readiness: enabled, fresh GPS and IMU, recent speed above the arming floor. */
  armed: boolean;
  armReason: ArmReason;
};

export const INITIAL_LIVE: LiveState = {
  connection: 'connecting',
  link: null,
  btOff: false,
  lastOkAt: null,
  status: null,
  alert: null,
  alertSupported: null,
  calibrating: false,
  physio: null,
  physioSupported: null,
  speedKmh: null,
  gpsAt: null,
  location: null,
  armed: false,
  armReason: 'no_gps',
};

export const useLive = create<LiveState>(() => INITIAL_LIVE);

export const setLive = (patch: Partial<LiveState>) => useLive.setState(patch);
