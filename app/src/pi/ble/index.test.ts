import { FakeBleLink } from './fake-link';
import { getBleLink, setBleLinkForTest } from './index';

describe('BLE index', () => {
  afterEach(() => {
    setBleLinkForTest(null);
  });

  it('returns a FakeBleLink singleton in Jest environment', () => {
    const link1 = getBleLink();
    const link2 = getBleLink();
    expect(link1).toBeInstanceOf(FakeBleLink);
    expect(link1).toBe(link2);
  });

  it('allows overriding the link via setBleLinkForTest', () => {
    const custom = new FakeBleLink();
    setBleLinkForTest(custom);
    expect(getBleLink()).toBe(custom);

    setBleLinkForTest(null);
    expect(getBleLink()).not.toBe(custom);
    expect(getBleLink()).toBeInstanceOf(FakeBleLink);
  });
});
