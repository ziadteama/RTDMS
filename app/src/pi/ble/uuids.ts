/**
 * GATT UUIDs for the Pi ↔ phone link.
 * Mirrors pi/src/rtdms_pi/ble/uuids.py and contracts/pi-link/CONTRACT.md.
 */

export const SERVICE_UUID = '0000fff0-0000-1000-8000-00805f9b34fb';
export const GARMIN_CHAR_UUID = '1375193a-7edb-4a34-b3f2-18130239c8a8';

export const CHAR = {
  ALERT: 1,
  STATUS: 2,
  PHYSIO: 3,
  SETTINGS: 4,
  COMMAND: 5,
  RESULT: 6,
  INCIDENT: 7,
  CLOCK: 8,
  AUTH: 9,
  HEALTH: 10,
} as const;

export type CharName = keyof typeof CHAR;

export function phoneUuid(nn: number): string {
  if (!Number.isInteger(nn) || nn < 1 || nn > 10) {
    throw new Error('unknown phone characteristic');
  }
  return `1375193a-7edb-4a34-b3f2-18130239${nn.toString(16).padStart(4, '0')}`;
}

export const CHAR_UUID = {
  ALERT: phoneUuid(CHAR.ALERT),
  STATUS: phoneUuid(CHAR.STATUS),
  PHYSIO: phoneUuid(CHAR.PHYSIO),
  SETTINGS: phoneUuid(CHAR.SETTINGS),
  COMMAND: phoneUuid(CHAR.COMMAND),
  RESULT: phoneUuid(CHAR.RESULT),
  INCIDENT: phoneUuid(CHAR.INCIDENT),
  CLOCK: phoneUuid(CHAR.CLOCK),
  AUTH: phoneUuid(CHAR.AUTH),
  HEALTH: phoneUuid(CHAR.HEALTH),
} as const;
