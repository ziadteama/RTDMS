import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { FakeBleLink } from '@/pi/ble/fake-link';
import { BleTransport } from '@/pi/ble/transport';
import { parseAlert, parsePhysio, parseStatus } from '@/pi/parse';
import { HttpTransport } from '@/pi/transport';
import { INITIAL_LIVE, useLive } from '@/state/live';

import { startBlePush } from './poller-ble';

const fixture = (name: string): unknown => JSON.parse(readFileSync(resolve(__dirname, '../../../contracts/pi-link/fixtures', `${name}.json`), 'utf8'));

test('both BLE consumers populate fields from the contract fixtures', async () => {
  jest.useFakeTimers();
  useLive.setState(INITIAL_LIVE);
  const link = new FakeBleLink();
  link.setState('online');
  const transport = new BleTransport(link, new HttpTransport('http://unused'));
  const stop = startBlePush(link);
  try {
    for (const kind of ['status', 'physio', 'alert'] as const) link.emit(kind, fixture(kind));
    const live = useLive.getState();
    expect(live.status?.drowsiness).toMatchObject({ state: 'drowsy', perclos: 0.31, calibrated: true });
    expect(live.status?.hybrid).toMatchObject({ call: false, texting: true, p: 0.91 });
    expect(live.physio?.hrv).toMatchObject({ state: 'valid', rmssd_ms: 35.1, quality: 'good' });
    expect(live.alert).toEqual(fixture('alert'));
    expect(parseStatus(await transport.get('/status'))).toEqual(live.status);
    expect(parsePhysio(await transport.get('/physio'))).toEqual(live.physio);
    expect(parseAlert(await transport.get('/alert'))).toEqual(live.alert);
  } finally {
    stop();
    transport.dispose();
    jest.useRealTimers();
  }
});
