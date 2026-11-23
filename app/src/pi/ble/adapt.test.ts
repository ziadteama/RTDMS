import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { parseAlert, parsePhysio, parseStatus } from '../parse';
import { adaptAlert, adaptPhysio, adaptStatus } from './adapt';

const fixture = (name: string): unknown => JSON.parse(readFileSync(resolve(__dirname, '../../../../contracts/pi-link/fixtures', `${name}.json`), 'utf8'));

test('contract status populates HTTP-shaped drowsiness and phone fields', () => {
  expect(parseStatus(adaptStatus(fixture('status')))).toMatchObject({
    fps: 14.3, face: true, temp_c: 64.2,
    drowsiness: { state: 'drowsy', perclos: 0.31, openness: 0.31, blink_rate: 9.5, closure_ms: 2400, calibrated: true },
    hybrid: { call: false, texting: true, p: 0.91 },
  });
});

test('contract physio preserves v2 fields', () => {
  expect(parsePhysio(adaptPhysio(fixture('physio')))).toEqual(fixture('physio'));
});

test('contract alert already matches the HTTP shape', () => {
  expect(parseAlert(adaptAlert(fixture('alert')))).toEqual(fixture('alert'));
});

test.each([
  ['status', adaptStatus, ['fps', 'face', 'state']],
  ['physio', adaptPhysio, ['watch_connected', 't']],
  ['alert', adaptAlert, ['pattern', 'reasons', 't']],
] as const)('%s drops missing required fields', (name, adapt, fields) => {
  for (const field of fields) {
    const value = { ...(fixture(name) as Record<string, unknown>) };
    delete value[field];
    expect(adapt(value)).toBeNull();
  }
  expect(adapt(null)).toBeNull();
});

test('ignores unknown nested fields rather than accepting a second wire shape', () => {
  expect(adaptStatus({ fps: 1, face: true, state: 'alert', drowsiness: { perclos: 0.9 }, perclos_valid: true }))
    .toEqual({ fps: 1, face: true, drowsiness: { state: 'alert', face: true }, hybrid: { face: true } });
  expect(parsePhysio(adaptPhysio({ watch_connected: true, t: 1 } ))?.hrv_state).toBeNull();
});

test('invalid required field types are dropped', () => {
  expect(adaptStatus({ fps: 1, face: true, state: ['alert'] })).toBeNull();
  expect(adaptPhysio({ watch_connected: true, t: '1' })).toBeNull();
  expect(adaptAlert({ pattern: 'none', reasons: [1], t: 1 })).toBeNull();
});

test.each(['ok', 'calibrating', 'failed', 'lost', 'unknown', null, undefined, 1])('calibration %s survives adaptation and is validated', (calibration) => {
  const parsed = parseStatus(adaptStatus({ fps: 1, face: true, state: 'alert', calibration }));
  expect(parsed?.drowsiness?.calibration).toBe(['ok', 'calibrating', 'failed', 'lost'].includes(calibration as string) ? calibration : null);
});
