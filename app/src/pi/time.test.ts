import { payloadTime } from './time';
import { parseAlert, parsePhysio } from './parse';

test('uses rounded phone seconds and arrival time otherwise', () => {
  expect(payloadTime({ t: 123.4567, t_src: 'phone' }, 999)).toBe(123457);
  expect(payloadTime({ t: 123, t_src: 'pi' }, 999)).toBe(999);
  expect(payloadTime({ t: 123 }, 999)).toBe(999);
});

test.each([undefined, null, '123', NaN, Infinity])('drops bad required time %s', (t) => {
  expect(parsePhysio({ watch_connected: true, t })).toBeNull();
  expect(parseAlert({ pattern: 'none', reasons: [], t })).toBeNull();
});

test('required fields and optional unknown fields remain tolerant', () => {
  expect(parsePhysio({ t: 1 })).toBeNull();
  expect(parseAlert({ pattern: 'none', t: 1 })).toBeNull();
  expect(parsePhysio({ watch_connected: true, t: 1, worn: 'yes', quality: 'unknown' }))
    .toMatchObject({ worn: null, quality: null, hr_baseline_bpm: null, hr_delta_bpm: null, hr_trend_bpm_per_10min: null });
});
