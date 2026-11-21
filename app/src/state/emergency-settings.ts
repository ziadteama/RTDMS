export type SosCountdownSeconds = 30 | 45 | 60;
export const validEmergencyNumber = (value: unknown): value is string =>
  typeof value === 'string' && /^\+?[0-9]{3,15}$/.test(value);
export const validCountdown = (value: unknown): value is SosCountdownSeconds =>
  value === 30 || value === 45 || value === 60;

/** Validate both edits and persisted values, migrating the previous number key. */
export function emergencySettings(value: Record<string, unknown>) {
  const number = value.emergencyNumber ?? value.ambulanceNumber;
  return {
    ...(validEmergencyNumber(number) ? { emergencyNumber: number } : {}),
    ...(validCountdown(value.sosCountdownSeconds) ? { sosCountdownSeconds: value.sosCountdownSeconds } : {}),
  };
}
