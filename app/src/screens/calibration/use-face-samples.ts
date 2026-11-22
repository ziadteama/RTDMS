import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  createFakeFaceSource,
  isFaceViewAvailable,
  useSettings,
  type FaceSample,
  type FakeScript,
} from './adapters';

export type UseFaceSamplesOptions = {
  script?: FakeScript;
  forceFake?: boolean;
};

export type UseFaceSamplesReturn = {
  latestSample: FaceSample | null;
  isNative: boolean;
  script: FakeScript;
  onFace: (sample: FaceSample) => void;
  subscribe: (cb: (sample: FaceSample) => void) => () => void;
};

const VALID_SCRIPTS = new Set<FakeScript>([
  'openThenClosed',
  'noFace',
  'tooDark',
  'headTurned',
  'eyesNotShut',
]);

function parseScript(param?: string): FakeScript | undefined {
  if (param && VALID_SCRIPTS.has(param as FakeScript)) {
    return param as FakeScript;
  }
  return undefined;
}

export function useFaceSamples(options?: UseFaceSamplesOptions): UseFaceSamplesReturn {
  let paramScript: FakeScript | undefined;
  try {
    const params = useLocalSearchParams<{ faceScript?: string }>();
    paramScript = parseScript(params?.faceScript);
  } catch {
    paramScript = undefined;
  }

  const demo = useSettings((s) => s.demo);
  const nativeAvailable = isFaceViewAvailable();
  const shouldUseFake = Boolean(options?.forceFake || demo || !nativeAvailable || paramScript);
  const script: FakeScript = paramScript ?? options?.script ?? 'openThenClosed';

  const [latestSample, setLatestSample] = useState<FaceSample | null>(null);
  const subscribersRef = useRef<Set<(sample: FaceSample) => void>>(new Set());

  const subscribe = useCallback((cb: (sample: FaceSample) => void) => {
    subscribersRef.current.add(cb);
    return () => {
      subscribersRef.current.delete(cb);
    };
  }, []);

  const onFace = useCallback((sample: FaceSample) => {
    setLatestSample(sample);
    for (const sub of subscribersRef.current) {
      sub(sample);
    }
  }, []);

  useEffect(() => {
    if (!shouldUseFake) return;
    const fakeSource = createFakeFaceSource({ script, intervalMs: 66 });
    const unsubscribe = fakeSource.subscribe((sample) => {
      setLatestSample(sample);
      for (const sub of subscribersRef.current) {
        sub(sample);
      }
    });
    return () => {
      unsubscribe();
    };
  }, [shouldUseFake, script]);

  return {
    latestSample,
    isNative: !shouldUseFake,
    script,
    onFace,
    subscribe,
  };
}
