import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import Ajv2020 from 'ajv/dist/2020';

import {
  authPayload,
  clockPayload,
  commandPayload,
  decode,
  encode,
  incidentPayload,
} from './codec';

describe('BLE wire codec', () => {
  describe('encode & decode', () => {
    it('round trips valid JSON objects', () => {
      const obj = { test: 'roundtrip', n: 42, arr: [1, 2, 3], nested: { flag: true } };
      const encoded = encode(obj);
      expect(typeof encoded).toBe('string');
      const decoded = decode(encoded);
      expect(decoded).toEqual(obj);
    });

    it('handles unicode / UTF-8 strings correctly', () => {
      const obj = { message: '🚗 Speed: 60 km/h, temperature: 25°C', symbol: '✓' };
      const encoded = encode(obj);
      expect(decode(encoded)).toEqual(obj);
    });

    it('returns null on invalid base64 input', () => {
      expect(decode(null)).toBeNull();
      expect(decode(undefined)).toBeNull();
      expect(decode(123)).toBeNull();
      expect(decode('')).toBeNull();
      expect(decode('not-base-64!!')).toBeNull();
      expect(decode('abc')).toBeNull(); // not multiple of 4
    });

    it('returns null on valid base64 but invalid JSON', () => {
      // base64 for "not valid json text"
      const badJsonB64 = Buffer.from('not valid json {', 'utf8').toString('base64');
      expect(decode(badJsonB64)).toBeNull();
    });

    it('throws if encoded payload exceeds 512 bytes limit', () => {
      const largeObj = { data: 'x'.repeat(600) };
      expect(() => encode(largeObj)).toThrow(/exceeds 512 B limit/);
    });
  });

  describe('contract fixture validation against schemas (Ajv2020)', () => {
    const schemasDir = resolve(__dirname, '../../../../contracts/pi-link/schemas');
    const fixturesDir = resolve(__dirname, '../../../../contracts/pi-link/fixtures');

    const ajv = new Ajv2020({ allErrors: true });

    // Preload all schemas into Ajv
    const schemaFiles = readdirSync(schemasDir).filter((f) => f.endsWith('.schema.json'));
    const schemas = new Map<string, object>();
    for (const file of schemaFiles) {
      const schemaName = file.replace('.schema.json', '');
      const content = JSON.parse(readFileSync(resolve(schemasDir, file), 'utf8'));
      ajv.addSchema(content, schemaName);
      schemas.set(schemaName, content);
    }

    const fixtures = [
      'alert',
      'auth',
      'clock',
      'command',
      'command_result',
      'health',
      'incident_item',
      'incident_request',
      'incident_response',
      'physio',
      'settings',
      'status',
    ];

    for (const fixtureName of fixtures) {
      it(`validates ${fixtureName}.json against ${fixtureName}.schema.json`, () => {
        const fixturePath = resolve(fixturesDir, `${fixtureName}.json`);
        if (!existsSync(fixturePath)) return;
        const fixture = JSON.parse(readFileSync(fixturePath, 'utf8'));
        const validator = ajv.getSchema(fixtureName);
        expect(validator).toBeDefined();
        if (!validator) return;
        const valid = validator(fixture);
        expect(validator.errors).toBeNull();
        expect(valid).toBe(true);
      });
    }

    it('asserts that encode of alert, status, and physio fixtures is <= 240 bytes', () => {
      for (const charName of ['alert', 'status', 'physio']) {
        const fixturePath = resolve(fixturesDir, `${charName}.json`);
        const fixture = JSON.parse(readFileSync(fixturePath, 'utf8'));
        const jsonBytes = new TextEncoder().encode(JSON.stringify(fixture));
        expect(jsonBytes.length).toBeLessThanOrEqual(240);
        // Also verify encode() succeeds without error
        const encoded = encode(fixture);
        expect(decode(encoded)).toEqual(fixture);
      }
    });

    describe('codec payload builders match contract schemas', () => {
      it('authPayload produces valid auth schema payload', () => {
        const authSchema = ajv.getSchema('auth');
        expect(authSchema).toBeDefined();

        const payload1 = authPayload('1234567890abcdef');
        expect(authSchema!(payload1)).toBe(true);

        const payload2 = authPayload('k3Jx9mQ2pL7vN4wR8tY1', 1);
        expect(authSchema!(payload2)).toBe(true);
      });

      it('clockPayload produces valid clock schema payload', () => {
        const clockSchema = ajv.getSchema('clock');
        expect(clockSchema).toBeDefined();

        const payload = clockPayload(1795189202400);
        expect(clockSchema!(payload)).toBe(true);
      });

      it('commandPayload produces valid command schema payload', () => {
        const commandSchema = ajv.getSchema('command');
        expect(commandSchema).toBeDefined();

        const p1 = commandPayload('test_alert', { pattern: 'max', id: 'c1' });
        expect(commandSchema!(p1)).toBe(true);

        const p2 = commandPayload('calibrate');
        expect(commandSchema!(p2)).toBe(true);

        const calFixture = JSON.parse(
          readFileSync(resolve(fixturesDir, 'phone_calibration.json'), 'utf8'),
        );
        const p3 = commandPayload('calibrate', { profile: calFixture });
        expect(commandSchema!(p3)).toBe(true);
      });

      it('incidentPayload produces valid incident_request schema payload', () => {
        const incidentSchema = ajv.getSchema('incident_request');
        expect(incidentSchema).toBeDefined();

        const payload = incidentPayload({
          t_crash: 1795189202400,
          g_peak: 6.4,
          lat: 31.20012,
          lon: 29.91871,
          client_id: '7d3c0f0e-5c0b-4a0b-9a77-1a2b3c4d5e6f',
        });
        expect(incidentSchema!(payload)).toBe(true);
      });
    });
  });
});
