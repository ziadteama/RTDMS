import { FakeBleLink } from './fake-link';
import type { BleLink } from './types';

let current: BleLink | null = null;

/**
 * TEMPORARY (orchestrator): always the fake. The BLE implementer replaces this with: real
 * ble-plx BleLink (lazy require) on Android, FakeBleLink on web and in Jest.
 */
export function getBleLink(): BleLink {
  return (current ??= new FakeBleLink());
}

/** Tests: install a link (or null to reset to the default). */
export function setBleLinkForTest(link: BleLink | null) {
  current = link;
}
