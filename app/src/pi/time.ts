import type { PayloadTime } from './types';

/** Only phone-synchronized payload time is suitable for the trip timeline. */
export function payloadTime(payload: PayloadTime, arrival = Date.now()): number {
  return payload.t_src === 'phone' && payload.t !== undefined ? Math.round(payload.t * 1000) : arrival;
}
