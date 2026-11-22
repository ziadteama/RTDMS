import { getInstallId, useSecure } from './secure';

const mockStore = new Map<string, string>();

jest.mock('expo-secure-store', () => ({
  getItem: jest.fn((k: string) => mockStore.get(k) ?? null),
  setItem: jest.fn((k: string, v: string) => {
    mockStore.set(k, v);
  }),
  deleteItemAsync: jest.fn(async (k: string) => {
    mockStore.delete(k);
  }),
}));

describe('getInstallId persistence', () => {
  beforeEach(() => {
    mockStore.clear();
    useSecure.getState().wipe();
  });

  it('creates random UUID on first run and persists across calls', () => {
    const id1 = getInstallId();
    expect(id1).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);

    const id2 = getInstallId();
    expect(id2).toBe(id1);
  });

  it('generates a new UUID after wipe()', () => {
    const id1 = getInstallId();
    useSecure.getState().wipe();
    const id2 = getInstallId();
    expect(id2).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    // Almost impossible to be identical with random UUID v4
    expect(id2).not.toBe(id1);
  });
});

describe('Pi token', () => {
  beforeEach(() => {
    mockStore.clear();
    useSecure.getState().wipe();
  });

  it('is stored under sahi.pi_token in the secure store and cleared by wipe()', () => {
    useSecure.getState().setPiToken('k3Jx9mQ2pL7vN4wR8tY1');
    expect(useSecure.getState().piToken).toBe('k3Jx9mQ2pL7vN4wR8tY1');
    expect(JSON.parse(mockStore.get('sahi.pi_token')!)).toBe('k3Jx9mQ2pL7vN4wR8tY1');
    useSecure.getState().wipe();
    expect(useSecure.getState().piToken).toBeNull();
    expect(mockStore.has('sahi.pi_token')).toBe(false);
  });
});
