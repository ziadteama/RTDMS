import { createFakeFaceSource } from '../FakeFaceSource';

describe('FakeFaceSource', () => {
  describe('determinism', () => {
    it('produces identical samples for two sources initialized with the same script', () => {
      let t = 100000;
      const fakeNow = () => t;

      const source1 = createFakeFaceSource({ script: 'openThenClosed', now: fakeNow });
      const source2 = createFakeFaceSource({ script: 'openThenClosed', now: fakeNow });

      const samples1 = [
        source1.getNextSample(t),
        source1.getNextSample((t += 1000)),
        source1.getNextSample((t += 5000)),
        source1.getNextSample((t += 8000)),
      ];

      t = 100000;
      const samples2 = [
        source2.getNextSample(t),
        source2.getNextSample((t += 1000)),
        source2.getNextSample((t += 5000)),
        source2.getNextSample((t += 8000)),
      ];

      expect(samples1).toEqual(samples2);
    });
  });

  describe('script shapes', () => {
    it('openThenClosed cycles 12s open (~0.30) and 4s closed (~0.10)', () => {
      const start = 1000;
      const source = createFakeFaceSource({
        script: 'openThenClosed',
        now: () => start,
      });

      // At 2s (open phase)
      const openSample = source.getNextSample(start + 2000);
      expect(openSample.faceFound).toBe(true);
      expect(openSample.earValid).toBe(true);
      expect(openSample.ear).toBeGreaterThan(0.28);
      expect(openSample.ear).toBeLessThan(0.32);
      expect(openSample.earLeft).toBe(openSample.ear);
      expect(openSample.earRight).toBe(openSample.ear);

      // At 14s (closed phase)
      const closedSample = source.getNextSample(start + 14000);
      expect(closedSample.faceFound).toBe(true);
      expect(closedSample.earValid).toBe(true);
      expect(closedSample.ear).toBeGreaterThan(0.08);
      expect(closedSample.ear).toBeLessThan(0.12);

      // At 17s (back to open phase: 17000 % 16000 = 1000ms < 12000ms)
      const openSample2 = source.getNextSample(start + 17000);
      expect(openSample2.ear).toBeGreaterThan(0.28);
    });

    it('noFace outputs faceFound: false and nulls', () => {
      const source = createFakeFaceSource({ script: 'noFace' });
      const sample = source.getNextSample(5000);

      expect(sample.faceFound).toBe(false);
      expect(sample.ear).toBeNull();
      expect(sample.earLeft).toBeNull();
      expect(sample.earRight).toBeNull();
      expect(sample.earValid).toBe(false);
      expect(sample.yaw).toBeNull();
      expect(sample.pitch).toBeNull();
      expect(sample.faceBoxFraction).toBe(0);
      expect(sample.luma).toBe(120);
    });

    it('tooDark sets luma to 20', () => {
      const source = createFakeFaceSource({ script: 'tooDark' });
      const sample = source.getNextSample(1000);

      expect(sample.faceFound).toBe(true);
      expect(sample.luma).toBe(20);
      expect(sample.earValid).toBe(true);
      expect(sample.ear).toBeGreaterThan(0.28);
    });

    it('headTurned sets yaw 40 and marks earValid false with ear null', () => {
      const source = createFakeFaceSource({ script: 'headTurned' });
      const sample = source.getNextSample(1000);

      expect(sample.faceFound).toBe(true);
      expect(sample.yaw).toBe(40);
      expect(sample.earValid).toBe(false);
      expect(sample.ear).toBeNull();
      expect(sample.earLeft).toBeGreaterThan(0.28);
      expect(sample.earRight).toBeGreaterThan(0.28);
    });

    it('eyesNotShut closes only down to ~0.27', () => {
      const start = 1000;
      const source = createFakeFaceSource({
        script: 'eyesNotShut',
        now: () => start,
      });

      // At 13s (closed phase)
      const closedSample = source.getNextSample(start + 13000);
      expect(closedSample.faceFound).toBe(true);
      expect(closedSample.earValid).toBe(true);
      expect(closedSample.ear).toBeGreaterThan(0.25);
      expect(closedSample.ear).toBeLessThan(0.29);
    });
  });

  describe('subscribe and unsubscribe', () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('emits samples at specified interval and stops on unsubscribe', () => {
      const samples: any[] = [];
      const source = createFakeFaceSource({
        script: 'openThenClosed',
        intervalMs: 100,
      });

      const unsubscribe = source.subscribe((s) => {
        samples.push(s);
      });

      expect(samples).toHaveLength(0);

      jest.advanceTimersByTime(250);
      expect(samples).toHaveLength(2);

      unsubscribe();
      jest.advanceTimersByTime(300);
      expect(samples).toHaveLength(2);
    });
  });
});
