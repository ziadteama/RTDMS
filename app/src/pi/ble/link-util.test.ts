import { computeBackoff, matchesTarget, ResultRouter } from './link-util';

describe('link-util', () => {
  describe('computeBackoff', () => {
    it('computes exponential backoff with zero jitter', () => {
      const noJitter = () => 0.5;
      expect(computeBackoff(0, noJitter)).toBe(1000);
      expect(computeBackoff(1, noJitter)).toBe(2000);
      expect(computeBackoff(2, noJitter)).toBe(4000);
      expect(computeBackoff(3, noJitter)).toBe(8000);
      expect(computeBackoff(4, noJitter)).toBe(15000);
      expect(computeBackoff(10, noJitter)).toBe(15000);
    });

    it('applies ±20% jitter bounds', () => {
      const minJitter = () => 0.0; // -20%
      const maxJitter = () => 1.0; // +20%
      expect(computeBackoff(0, minJitter)).toBe(800);
      expect(computeBackoff(0, maxJitter)).toBe(1200);
      expect(computeBackoff(4, minJitter)).toBe(12000);
      expect(computeBackoff(4, maxJitter)).toBe(18000);
    });
  });

  describe('matchesTarget', () => {
    const target = { name: 'RTDMS-Pi' };

    it('matches when device.name equals target name', () => {
      expect(matchesTarget({ name: 'RTDMS-Pi' }, target)).toBe(true);
      expect(matchesTarget({ name: 'Other' }, target)).toBe(false);
    });

    it('matches when device.localName equals target name', () => {
      expect(matchesTarget({ name: null, localName: 'RTDMS-Pi' }, target)).toBe(true);
      expect(matchesTarget({ name: undefined, localName: 'Other' }, target)).toBe(false);
    });

    it('returns false when target name is empty or device has no name', () => {
      expect(matchesTarget({ name: null, localName: null }, target)).toBe(false);
      expect(matchesTarget({ name: 'RTDMS-Pi' }, { name: '' })).toBe(false);
    });
  });

  describe('ResultRouter', () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('routes result to pending command promise', async () => {
      const router = new ResultRouter();
      const p = router.registerCommand(4000);
      expect(router.hasPending()).toBe(true);

      const routed = router.routeResult({ ok: true, id: 'c1' });
      expect(routed).toBe(true);
      expect(router.hasPending()).toBe(false);

      await expect(p).resolves.toEqual({ ok: true, id: 'c1' });
    });

    it('routes result to pending incident promise', async () => {
      const router = new ResultRouter();
      const p = router.registerIncident(6000);
      expect(router.hasPending()).toBe(true);

      const routed = router.routeResult({ ok: true, id: '2026-11-20T15-40-02-400Z' });
      expect(routed).toBe(true);
      expect(router.hasPending()).toBe(false);

      await expect(p).resolves.toEqual({ ok: true, id: '2026-11-20T15-40-02-400Z' });
    });

    it('rejects concurrent command calls with busy', async () => {
      const router = new ResultRouter();
      const p1 = router.registerCommand(4000);
      await expect(router.registerCommand(4000)).rejects.toThrow('busy');

      router.routeResult({ ok: true });
      await expect(p1).resolves.toEqual({ ok: true });
    });

    it('rejects concurrent incident calls with busy', async () => {
      const router = new ResultRouter();
      const p1 = router.registerIncident(6000);
      await expect(router.registerIncident(6000)).rejects.toThrow('busy');

      router.routeResult({ ok: true });
      await expect(p1).resolves.toEqual({ ok: true });
    });

    it('rejects on timeout and clears pending state', async () => {
      const router = new ResultRouter();
      const p = router.registerCommand(1000);

      jest.advanceTimersByTime(1000);

      await expect(p).rejects.toThrow(/timed out/);
      expect(router.hasPending()).toBe(false);
    });

    it('rejectAll rejects pending command and incident on link loss', async () => {
      const router = new ResultRouter();
      const pCmd = router.registerCommand(4000);
      const pInc = router.registerIncident(6000);

      router.rejectAll(new Error('BLE link lost'));

      await expect(pCmd).rejects.toThrow('BLE link lost');
      await expect(pInc).rejects.toThrow('BLE link lost');
      expect(router.hasPending()).toBe(false);
    });
  });
});
