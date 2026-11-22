import type { FaceSample } from './SahiNative.types';

export type FakeScript =
  | 'openThenClosed'
  | 'noFace'
  | 'tooDark'
  | 'headTurned'
  | 'eyesNotShut';

export type FakeFaceSourceOptions = {
  script: FakeScript;
  intervalMs?: number;
  now?: () => number;
};

export type FakeFaceSource = {
  subscribe: (cb: (sample: FaceSample) => void) => () => void;
  getNextSample: (timeMs?: number) => FaceSample;
};

function createRng(seed = 1337) {
  let s = seed >>> 0;
  return function next(): number {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return (t >>> 0) / 4294967296;
  };
}

export function createFakeFaceSource({
  script,
  intervalMs = 66,
  now = () => Date.now(),
}: FakeFaceSourceOptions): FakeFaceSource {
  const startMs = now();
  const rng = createRng(1337);

  function generateSample(currentTime: number): FaceSample {
    const elapsedMs = Math.max(0, currentTime - startMs);
    // Small deterministic noise between -0.01 and +0.01
    const noise = (rng() - 0.5) * 0.02;
    const yawNoise = (rng() - 0.5) * 2.0;
    const pitchNoise = (rng() - 0.5) * 2.0;

    switch (script) {
      case 'noFace':
        return {
          faceFound: false,
          ear: null,
          earLeft: null,
          earRight: null,
          earValid: false,
          yaw: null,
          pitch: null,
          faceBoxFraction: 0,
          luma: 120,
          t: currentTime,
        };

      case 'tooDark': {
        const ear = Math.round((0.3 + noise) * 1000) / 1000;
        return {
          faceFound: true,
          ear,
          earLeft: ear,
          earRight: ear,
          earValid: true,
          yaw: Math.round(yawNoise * 10) / 10,
          pitch: Math.round(pitchNoise * 10) / 10,
          faceBoxFraction: 0.65,
          luma: 20,
          t: currentTime,
        };
      }

      case 'headTurned': {
        const earValue = Math.round((0.3 + noise) * 1000) / 1000;
        return {
          faceFound: true,
          ear: null, // Invalidated by |yaw| > 30
          earLeft: earValue,
          earRight: earValue,
          earValid: false,
          yaw: 40,
          pitch: Math.round(pitchNoise * 10) / 10,
          faceBoxFraction: 0.65,
          luma: 130,
          t: currentTime,
        };
      }

      case 'eyesNotShut': {
        // 12s open (~0.30), 4s closed (~0.27)
        const cycle = elapsedMs % 16000;
        const isOpen = cycle < 12000;
        const targetEar = isOpen ? 0.3 : 0.27;
        const ear = Math.round((targetEar + noise) * 1000) / 1000;
        return {
          faceFound: true,
          ear,
          earLeft: ear,
          earRight: ear,
          earValid: true,
          yaw: Math.round(yawNoise * 10) / 10,
          pitch: Math.round(pitchNoise * 10) / 10,
          faceBoxFraction: 0.65,
          luma: 130,
          t: currentTime,
        };
      }

      case 'openThenClosed':
      default: {
        // 12s open (~0.30), 4s closed (~0.10)
        const cycle = elapsedMs % 16000;
        const isOpen = cycle < 12000;
        const targetEar = isOpen ? 0.3 : 0.1;
        const ear = Math.round((targetEar + noise) * 1000) / 1000;
        return {
          faceFound: true,
          ear,
          earLeft: ear,
          earRight: ear,
          earValid: true,
          yaw: Math.round(yawNoise * 10) / 10,
          pitch: Math.round(pitchNoise * 10) / 10,
          faceBoxFraction: 0.65,
          luma: 130,
          t: currentTime,
        };
      }
    }
  }

  return {
    getNextSample(timeMs?: number) {
      return generateSample(timeMs ?? now());
    },
    subscribe(cb: (sample: FaceSample) => void) {
      const intervalId = setInterval(() => {
        cb(generateSample(now()));
      }, intervalMs);

      return () => {
        clearInterval(intervalId);
      };
    },
  };
}
