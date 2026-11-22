import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { validatePhoneCalibration } from './calibrate-validator';

describe('validatePhoneCalibration', () => {
  const fixturePath = resolve(
    __dirname,
    '../../contracts/pi-link/fixtures/phone_calibration.json',
  );
  const fixture = JSON.parse(readFileSync(fixturePath, 'utf8'));

  it('accepts the golden contract fixture', () => {
    const result = validatePhoneCalibration(fixture);
    expect(result).toEqual({ ok: true });
  });

  it('rejects invalid or missing source', () => {
    expect(validatePhoneCalibration({ ...fixture, source: 'pi' })).toEqual({
      ok: false,
      error: "source must be 'phone'",
    });
    expect(validatePhoneCalibration({ ...fixture, source: undefined })).toEqual({
      ok: false,
      error: "source must be 'phone'",
    });
  });

  it('rejects closed_ratio out of range [0.1, 0.8]', () => {
    expect(validatePhoneCalibration({ ...fixture, closed_ratio: 0.05 })).toEqual({
      ok: false,
      error: 'closed_ratio out of range [0.1, 0.8]',
    });
    expect(validatePhoneCalibration({ ...fixture, closed_ratio: 0.85 })).toEqual({
      ok: false,
      error: 'closed_ratio out of range [0.1, 0.8]',
    });
  });

  it('rejects ear separation < 0.04', () => {
    expect(
      validatePhoneCalibration({
        ...fixture,
        ear_open: 0.25,
        ear_closed: 0.23, // separation 0.02 < 0.04
      }),
    ).toEqual({
      ok: false,
      error: 'separation too small: ear_open - ear_closed < 0.04',
    });
  });

  it('rejects poor quality', () => {
    expect(validatePhoneCalibration({ ...fixture, quality: 'poor' })).toEqual({
      ok: false,
      error: 'rejected: signal quality is poor',
    });
  });

  it('rejects invalid sample counts', () => {
    expect(validatePhoneCalibration({ ...fixture, samples_open: 0 })).toEqual({
      ok: false,
      error: 'samples_open must be an integer >= 1',
    });
    expect(validatePhoneCalibration({ ...fixture, samples_closed: -1 })).toEqual({
      ok: false,
      error: 'samples_closed must be an integer >= 1',
    });
    expect(validatePhoneCalibration({ ...fixture, samples_open: 1.5 })).toEqual({
      ok: false,
      error: 'samples_open must be an integer >= 1',
    });
  });

  it('rejects non-object or null body', () => {
    expect(validatePhoneCalibration(null)).toEqual({
      ok: false,
      error: 'body must be a JSON object',
    });
    expect(validatePhoneCalibration('string')).toEqual({
      ok: false,
      error: 'body must be a JSON object',
    });
  });
});
