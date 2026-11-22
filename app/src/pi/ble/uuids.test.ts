import { CHAR, CHAR_UUID, GARMIN_CHAR_UUID, phoneUuid, SERVICE_UUID } from './uuids';

describe('BLE UUIDs', () => {
  it('defines the single Pi service UUID', () => {
    expect(SERVICE_UUID).toBe('0000fff0-0000-1000-8000-00805f9b34fb');
  });

  it('defines the Garmin characteristic UUID', () => {
    expect(GARMIN_CHAR_UUID).toBe('1375193a-7edb-4a34-b3f2-18130239c8a8');
  });

  it('defines the CHAR constant map from 1 to 10', () => {
    expect(CHAR.ALERT).toBe(1);
    expect(CHAR.STATUS).toBe(2);
    expect(CHAR.PHYSIO).toBe(3);
    expect(CHAR.SETTINGS).toBe(4);
    expect(CHAR.COMMAND).toBe(5);
    expect(CHAR.RESULT).toBe(6);
    expect(CHAR.INCIDENT).toBe(7);
    expect(CHAR.CLOCK).toBe(8);
    expect(CHAR.AUTH).toBe(9);
    expect(CHAR.HEALTH).toBe(10);
  });

  it('matches the literal UUID strings defined in CONTRACT.md', () => {
    expect(phoneUuid(1)).toBe('1375193a-7edb-4a34-b3f2-181302390001');
    expect(phoneUuid(2)).toBe('1375193a-7edb-4a34-b3f2-181302390002');
    expect(phoneUuid(3)).toBe('1375193a-7edb-4a34-b3f2-181302390003');
    expect(phoneUuid(4)).toBe('1375193a-7edb-4a34-b3f2-181302390004');
    expect(phoneUuid(5)).toBe('1375193a-7edb-4a34-b3f2-181302390005');
    expect(phoneUuid(6)).toBe('1375193a-7edb-4a34-b3f2-181302390006');
    expect(phoneUuid(7)).toBe('1375193a-7edb-4a34-b3f2-181302390007');
    expect(phoneUuid(8)).toBe('1375193a-7edb-4a34-b3f2-181302390008');
    expect(phoneUuid(9)).toBe('1375193a-7edb-4a34-b3f2-181302390009');
    expect(phoneUuid(10)).toBe('1375193a-7edb-4a34-b3f2-18130239000a');

    expect(CHAR_UUID.ALERT).toBe('1375193a-7edb-4a34-b3f2-181302390001');
    expect(CHAR_UUID.STATUS).toBe('1375193a-7edb-4a34-b3f2-181302390002');
    expect(CHAR_UUID.PHYSIO).toBe('1375193a-7edb-4a34-b3f2-181302390003');
    expect(CHAR_UUID.SETTINGS).toBe('1375193a-7edb-4a34-b3f2-181302390004');
    expect(CHAR_UUID.COMMAND).toBe('1375193a-7edb-4a34-b3f2-181302390005');
    expect(CHAR_UUID.RESULT).toBe('1375193a-7edb-4a34-b3f2-181302390006');
    expect(CHAR_UUID.INCIDENT).toBe('1375193a-7edb-4a34-b3f2-181302390007');
    expect(CHAR_UUID.CLOCK).toBe('1375193a-7edb-4a34-b3f2-181302390008');
    expect(CHAR_UUID.AUTH).toBe('1375193a-7edb-4a34-b3f2-181302390009');
    expect(CHAR_UUID.HEALTH).toBe('1375193a-7edb-4a34-b3f2-18130239000a');
  });

  it('throws on invalid characteristic numbers', () => {
    expect(() => phoneUuid(0)).toThrow('unknown phone characteristic');
    expect(() => phoneUuid(11)).toThrow('unknown phone characteristic');
    expect(() => phoneUuid(1.5)).toThrow('unknown phone characteristic');
  });
});
