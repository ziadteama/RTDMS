import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import Ajv2020 from 'ajv/dist/2020';

import {
  buildProfile,
  framingStatus,
  mad,
  median,
  openStateNoise,
  PhaseCollector,
  toPhoneCalibrationPayload,
} from './index';
import { assessQuality } from './stats';
import type { EarSample } from './types';

describe('Calibration math & algorithms (ported from Python dms_face)', () => {
  describe('median & MAD stats', () => {
    it('computes median for odd and even lengths correctly', () => {
      expect(median([])).toBeNull();
      expect(median([5])).toBe(5);
      expect(median([1, 5, 2])).toBe(2);
      expect(median([1, 2, 3, 4])).toBe(2.5);
    });

    it('computes MAD correctly and handles < 5 samples', () => {
      expect(mad([1, 2, 3])).toBeNull();
      // Values: [1, 2, 3, 4, 5], median = 3, diffs = [2, 1, 0, 1, 2], sorted = [0, 1, 1, 2, 2], median = 1
      expect(mad([1, 2, 3, 4, 5])).toBe(1);
    });

    // Mirroring test_open_state_noise_ignores_blinks from models/face/tests/test_core.py
    it('open_state_noise ignores blinks', () => {
      const baseCycle = [0.250, 0.252, 0.248, 0.251, 0.249, 0.250, 0.253, 0.247];
      let samples: number[] = [];
      for (let i = 0; i < 5; i++) {
        samples = samples.concat(baseCycle);
      }
      samples = samples.concat([0.06, 0.05, 0.07]); // 3 blinks

      const noise = openStateNoise(samples);
      expect(noise).not.toBeNull();
      expect(noise!).toBeLessThan(0.005);
    });
  });

  describe('assessQuality (mirroring test_quality_* from test_core.py)', () => {
    // Mirroring test_quality_separates_wide_and_narrow_eyes
    it('separates wide and narrow eyes based on SNR', () => {
      const wide = assessQuality(0.21, 0.005);
      const narrow = assessQuality(0.06, 0.005);

      expect(wide.quality).toBe('good');
      expect(wide.snr).toBeCloseTo(42.0, 1);

      expect(narrow.quality).toBe('poor');
      expect(narrow.snr).toBeCloseTo(12.0, 1);

      expect(assessQuality(0.06, 0.005, 0.30).quality).toBe('fair');
      expect(assessQuality(0.06, 0.005, 0.40).quality).toBe('good');
    });

    // Mirroring test_quality_handles_missing_noise_estimate
    it('handles missing noise estimate', () => {
      const result = assessQuality(0.2, null);
      expect(result.quality).toBe('unknown');
      expect(result.snr).toBeNull();
    });
  });

  describe('PhaseCollector', () => {
    it('discards the first 2 seconds during settling (2000 ms)', () => {
      const collector = new PhaseCollector(2000);

      // Pushing before 2000 ms -> settling, ignored
      const sample1: EarSample = {
        t: 500,
        ear: 0.3,
        earValid: true,
        faceFound: true,
        yaw: 0,
        pitch: 0,
        luma: 50,
        faceBoxFraction: 0.5,
      };
      expect(collector.push(sample1)).toBe(false);
      expect(collector.samplesCount).toBe(0);

      // Pushing at 2100 ms -> accepted
      const sample2: EarSample = {
        t: 2100,
        ear: 0.3,
        earValid: true,
        faceFound: true,
        yaw: 0,
        pitch: 0,
        luma: 50,
        faceBoxFraction: 0.5,
      };
      expect(collector.push(sample2)).toBe(true);
      expect(collector.samplesCount).toBe(1);
    });

    it('handles timestamps provided in milliseconds', () => {
      const collector = new PhaseCollector(2000);
      expect(
        collector.push({
          t: 1500, // 1500 ms -> settling
          ear: 0.3,
          earValid: true,
          faceFound: true,
          yaw: 0,
          pitch: 0,
          luma: 50,
          faceBoxFraction: 0.5,
        }),
      ).toBe(false);

      expect(
        collector.push({
          t: 2500, // 2500 ms -> valid
          ear: 0.3,
          earValid: true,
          faceFound: true,
          yaw: 0,
          pitch: 0,
          luma: 50,
          faceBoxFraction: 0.5,
        }),
      ).toBe(true);
    });

    it('tracks rejects for no_face, head_turned, and invalid ear', () => {
      const collector = new PhaseCollector(2000);

      // no_face
      collector.push({
        t: 3000,
        ear: null,
        earValid: false,
        faceFound: false,
        yaw: null,
        pitch: null,
        luma: 50,
        faceBoxFraction: 0.1,
      });

      // head_turned (|yaw| > 15)
      collector.push({
        t: 3100,
        ear: 0.25,
        earValid: false,
        faceFound: true,
        yaw: 20,
        pitch: 0,
        luma: 50,
        faceBoxFraction: 0.5,
      });

      // invalid_ear
      collector.push({
        t: 3200,
        ear: null,
        earValid: false,
        faceFound: true,
        yaw: 0,
        pitch: 0,
        luma: 50,
        faceBoxFraction: 0.5,
      });

      expect(collector.samplesCount).toBe(0);
      expect(collector.rejectCount).toBe(3);
      expect(collector.rejectBreakdown).toEqual({
        noFace: 1,
        headTurned: 1,
        invalidEar: 1,
        total: 3,
      });
    });
  });

  describe('buildProfile', () => {
    // Mirroring test_calibration_rejects_indistinct_endpoints from test_core.py
    it('rejects indistinct endpoints when separation < 0.04 (eyes_not_shut)', () => {
      const openPhase = { ear: 0.25, h: 0.5, v: 0.5, yaw: 0, pitch: 0, roll: 0, n: 200 };
      const closedPhase = { ear: 0.24, h: null, v: null, yaw: 0, pitch: 0, roll: 0, n: 60 };

      const result = buildProfile(openPhase, closedPhase);
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.reason).toBe('eyes_not_shut');
      }
    });

    // Mirroring test_calibration_accepts_good_endpoints from test_core.py
    it('accepts good endpoints with separation >= 0.04', () => {
      const openPhase = {
        ear: 0.28,
        h: 0.52,
        v: 0.49,
        yaw: 1.0,
        pitch: 20.0,
        roll: 0,
        n: 250,
        noise: 0.003,
      };
      const closedPhase = { ear: 0.09, h: null, v: null, yaw: 0, pitch: 0, roll: 0, n: 80 };

      const result = buildProfile(openPhase, closedPhase);
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.payload.ear_open).toBe(0.28);
        expect(result.payload.ear_closed).toBe(0.09);
        expect(result.payload.source).toBe('phone');
        expect(result.payload.closed_ratio).toBeCloseTo(0.09 / 0.28, 4);
        expect(result.payload.quality).toBe('good');
      }
    });

    it('rejects with too_dark when mean luma < 40', () => {
      const openPhase = { ear: 0.3, n: 100, meanLuma: 35 };
      const closedPhase = { ear: 0.1, n: 30, meanLuma: 35 };

      const result = buildProfile(openPhase, closedPhase);
      expect(result).toEqual({ ok: false, reason: 'too_dark' });
    });

    it('rejects with no_face when no face is found', () => {
      const openPhase = {
        ear: null,
        n: 0,
        rejects: { noFace: 50, headTurned: 0, invalidEar: 0, total: 50 },
      };
      const closedPhase = { ear: 0.1, n: 30 };

      const result = buildProfile(openPhase, closedPhase);
      expect(result).toEqual({ ok: false, reason: 'no_face' });
    });

    it('rejects with head_turned when rejects are primarily due to head orientation', () => {
      const openPhase = {
        ear: null,
        n: 0,
        rejects: { noFace: 2, headTurned: 40, invalidEar: 0, total: 42 },
      };
      const closedPhase = { ear: 0.1, n: 30 };

      const result = buildProfile(openPhase, closedPhase);
      expect(result).toEqual({ ok: false, reason: 'head_turned' });
    });

    it('rejects with too_few_samples when insufficient samples were collected', () => {
      const openPhase = { ear: 0.3, n: 4 }; // min open is 10
      const closedPhase = { ear: 0.1, n: 30 };

      const result = buildProfile(openPhase, closedPhase);
      expect(result).toEqual({ ok: false, reason: 'too_few_samples' });
    });
  });

  describe('framingStatus', () => {
    it('validates face in oval, lighting, and head alignment', () => {
      // Perfect framing
      expect(
        framingStatus({
          faceFound: true,
          faceBoxFraction: 0.5,
          luma: 50,
          yaw: 2,
          pitch: -3,
        }),
      ).toEqual({ faceInOval: true, lightOk: true, headStraight: true });

      // Face too small / outside oval
      expect(
        framingStatus({
          faceFound: true,
          faceBoxFraction: 0.15,
          luma: 50,
          yaw: 0,
          pitch: 0,
        }).faceInOval,
      ).toBe(false);

      // Too dark
      expect(
        framingStatus({
          faceFound: true,
          faceBoxFraction: 0.5,
          luma: 30,
          yaw: 0,
          pitch: 0,
        }).lightOk,
      ).toBe(false);

      // Head turned
      expect(
        framingStatus({
          faceFound: true,
          faceBoxFraction: 0.5,
          luma: 50,
          yaw: 25,
          pitch: 0,
        }).headStraight,
      ).toBe(false);
    });
  });

  describe('payload & JSON Schema validation against contracts/pi-link', () => {
    const schemaPath = resolve(
      __dirname,
      '../../../contracts/pi-link/schemas/phone_calibration.schema.json',
    );
    const fixturePath = resolve(
      __dirname,
      '../../../contracts/pi-link/fixtures/phone_calibration.json',
    );

    const schema = JSON.parse(readFileSync(schemaPath, 'utf8'));
    const fixture = JSON.parse(readFileSync(fixturePath, 'utf8'));
    const ajv = new Ajv2020({ allErrors: true });
    const validate = ajv.compile(schema);

    it('validates the golden fixture against the JSON schema', () => {
      const valid = validate(fixture);
      expect(validate.errors).toBeNull();
      expect(valid).toBe(true);
    });

    it('generates a payload matching the golden fixture shape and schema', () => {
      const generated = toPhoneCalibrationPayload({
        earOpen: fixture.ear_open,
        earClosed: fixture.ear_closed,
        snr: fixture.snr,
        quality: fixture.quality,
        samplesOpen: fixture.samples_open,
        samplesClosed: fixture.samples_closed,
        created: fixture.created,
      });

      // Keys match fixture shape
      expect(Object.keys(generated).sort()).toEqual(Object.keys(fixture).sort());

      // Validates against JSON schema
      const valid = validate(generated);
      expect(validate.errors).toBeNull();
      expect(valid).toBe(true);
    });

    it('clips closed_ratio to schema limits [0.1, 0.8]', () => {
      const low = toPhoneCalibrationPayload({
        earOpen: 1.0,
        earClosed: 0.05,
        snr: 40,
        quality: 'good',
        samplesOpen: 100,
        samplesClosed: 30,
      });
      expect(low.closed_ratio).toBe(0.1);

      const high = toPhoneCalibrationPayload({
        earOpen: 0.3,
        earClosed: 0.28,
        snr: 40,
        quality: 'good',
        samplesOpen: 100,
        samplesClosed: 30,
      });
      expect(high.closed_ratio).toBe(0.8);
    });
  });
});
