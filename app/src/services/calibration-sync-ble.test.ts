import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import Ajv2020 from 'ajv/dist/2020';

import type { PhoneCalibrationPayload } from '@/calibration/types';
import { FakeBleLink } from '@/pi/ble/fake-link';
import { setBleLinkForTest } from '@/pi/ble';
import { setLive } from '@/state/live';
import { useSettings } from '@/state/settings';

import {
  BleCalibrationTransport,
  clearCalibrationSyncState,
  defaultCalibrationTransport,
  syncEyeCalibration,
} from './calibration-sync';

jest.mock('expo-sqlite/kv-store', () => ({
  Storage: { getItemSync: jest.fn(() => null), setItemSync: jest.fn(), removeItemSync: jest.fn(), clearSync: jest.fn() },
}));

const contracts = resolve(__dirname, '../../../contracts/pi-link');
const readJson = (p: string) => JSON.parse(readFileSync(resolve(contracts, p), 'utf8'));

const payload: PhoneCalibrationPayload = readJson('fixtures/phone_calibration.json');

describe('BleCalibrationTransport', () => {
  let link: FakeBleLink;
  beforeEach(() => {
    link = new FakeBleLink();
    link.setState('online');
    setBleLinkForTest(link);
  });
  afterEach(() => setBleLinkForTest(null));

  it('sends a calibrate command that matches the contract schema', async () => {
    link.handlers.command = () => ({ ok: true });
    await new BleCalibrationTransport().send(payload);
    const body = link.written[0]!.body;
    expect(body).toEqual({ cmd: 'calibrate', profile: payload });
    const validate = new Ajv2020({ allErrors: true }).compile(readJson('schemas/command.schema.json'));
    expect(validate(body)).toBe(true);
  });

  it('maps ok:true to ok and ok:false to rejected', async () => {
    link.handlers.command = () => ({ ok: true });
    expect(await new BleCalibrationTransport().send(payload)).toBe('ok');
    link.handlers.command = () => ({ ok: false, error: 'poor quality' });
    expect(await new BleCalibrationTransport().send(payload)).toBe('rejected');
  });

  it('maps a throw or timeout to unreachable', async () => {
    link.handlers.command = () => {
      throw new Error('timeout');
    };
    expect(await new BleCalibrationTransport().send(payload)).toBe('unreachable');
    link.setState('offline');
    expect(await new BleCalibrationTransport().send(payload)).toBe('unreachable');
  });
});

describe('defaultCalibrationTransport', () => {
  const cal = { closedRatio: 0.38, earOpen: 0.29, earClosed: 0.11, snr: 46.2, quality: 'good' as const, at: 1795189202400, syncedAt: null };
  let link: FakeBleLink;
  beforeEach(() => {
    link = new FakeBleLink();
    setBleLinkForTest(link);
    useSettings.getState().reset();
    useSettings.getState().setEyeCalibration({ ...cal });
    setLive({ connection: 'online' });
    clearCalibrationSyncState();
    global.fetch = jest.fn().mockResolvedValue({ status: 200, ok: true } as Response);
  });
  afterEach(() => setBleLinkForTest(null));

  it('prefers Bluetooth while the link is online', async () => {
    link.setState('online');
    link.handlers.command = () => ({ ok: true });
    await defaultCalibrationTransport().send(payload);
    expect(link.written).toHaveLength(1);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('uses HTTP when the link is not online', async () => {
    expect(await defaultCalibrationTransport().send(payload)).toBe('ok');
    expect(link.written).toHaveLength(0);
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('syncEyeCalibration uses it by default and marks the calibration synced', async () => {
    link.setState('online');
    link.handlers.command = () => ({ ok: true });
    expect(await syncEyeCalibration()).toBe('ok');
    expect(useSettings.getState().eyeCalibration?.syncedAt).not.toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
