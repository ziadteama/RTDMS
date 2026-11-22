import { Platform } from 'react-native';

import { FakeBleLink } from './fake-link';
import type { BleLink } from './types';

let current: BleLink | null = null;

export function getBleLink(): BleLink {
  if (current) return current;
  const isJest = typeof process !== 'undefined' && Boolean(process.env?.JEST_WORKER_ID);
  if (Platform.OS === 'android' && !isJest) {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { PlxBleLink } = require('./link') as { PlxBleLink: new () => BleLink };
    current = new PlxBleLink();
  } else {
    current = new FakeBleLink();
  }
  return current;
}

export function setBleLinkForTest(link: BleLink | null): void {
  current = link;
}

export { BleTransport } from './transport';
export { FakeBleLink } from './fake-link';
export * from './types';
export * from './uuids';
export * from './codec';
export * from './permissions';
