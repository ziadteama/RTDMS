import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  PhaseCollector,
  SETTLE_MS,
  buildProfile,
  framingStatus,
  safeHaptic,
  safeSpeak,
  syncEyeCalibration,
  useSettings,
  type BuildProfileFailureReason,
  type CalibrationQuality,
  type CalibrationTransport,
  type FaceSample,
  type FramingStatus,
  type PhoneCalibrationPayload,
} from './adapters';

export type CalibrationStep = 'intro' | 'framing' | 'open' | 'closed' | 'result' | 'failed';

export const defaultNow = () => Date.now();

export type UseCalibrationMachineOptions = {
  subscribe: (cb: (sample: FaceSample) => void) => () => void;
  calOverride?: string;
  now?: () => number;
  transport?: CalibrationTransport;
};

export type UseCalibrationMachineReturn = {
  step: CalibrationStep;
  framing: FramingStatus;
  isStable: boolean;
  secondsRemaining: number;
  resultPayload: PhoneCalibrationPayload | null;
  failureReason: BuildProfileFailureReason | null;
  isSaved: boolean;
  isSynced: boolean;
  start: () => void;
  cancel: () => void;
  retry: () => void;
  save: () => void;
};

const DEFAULT_FRAMING: FramingStatus = {
  faceInOval: false,
  lightOk: false,
  headStraight: false,
};

function getMockPayload(quality: CalibrationQuality = 'good'): PhoneCalibrationPayload {
  return {
    source: 'phone',
    closed_ratio: 0.38,
    ear_open: 0.29,
    ear_closed: 0.11,
    snr: 45.0,
    quality,
    samples_open: 120,
    samples_closed: 40,
    created: Date.now(),
  };
}

function parseOverride(override?: string) {
  if (override === 'framing') return { step: 'framing' as const, rem: 10, res: null, fail: null };
  if (override === 'open') return { step: 'open' as const, rem: 5, res: null, fail: null };
  if (override === 'closed') return { step: 'closed' as const, rem: 2, res: null, fail: null };
  if (override === 'fair') return { step: 'result' as const, rem: 0, res: getMockPayload('fair'), fail: null };
  if (override === 'poor') return { step: 'result' as const, rem: 0, res: getMockPayload('poor'), fail: null };
  if (override === 'good' || override === 'result') return { step: 'result' as const, rem: 0, res: getMockPayload('good'), fail: null };
  if (override === 'failure-dark') return { step: 'failed' as const, rem: 0, res: null, fail: 'too_dark' as const };
  if (override === 'failure-turned') return { step: 'failed' as const, rem: 0, res: null, fail: 'head_turned' as const };
  if (override === 'failure-eyes') return { step: 'failed' as const, rem: 0, res: null, fail: 'eyes_not_shut' as const };
  if (override && (override.startsWith('fail') || override === 'noFace')) {
    return { step: 'failed' as const, rem: 0, res: null, fail: 'no_face' as const };
  }
  return { step: 'intro' as const, rem: 10, res: null, fail: null };
}

export function useCalibrationMachine({
  subscribe,
  calOverride,
  now = defaultNow,
  transport,
}: UseCalibrationMachineOptions): UseCalibrationMachineReturn {
  let paramCal: string | undefined;
  try {
    const params = useLocalSearchParams<{ cal?: string }>();
    paramCal = params?.cal;
  } catch {
    paramCal = undefined;
  }

  const initial = parseOverride(calOverride ?? paramCal);
  const override = calOverride ?? paramCal;

  const nowRef = useRef(now);
  useEffect(() => {
    nowRef.current = now;
  }, [now]);

  const [step, setStep] = useState<CalibrationStep>(initial.step);
  const [framing, setFraming] = useState<FramingStatus>(() => ({
    faceInOval: initial.step === 'framing',
    lightOk: initial.step === 'framing',
    headStraight: initial.step === 'framing',
  }));
  const [isStable, setIsStable] = useState(initial.step === 'framing');
  const [secondsRemaining, setSecondsRemaining] = useState<number>(initial.rem);
  const [resultPayload, setResultPayload] = useState<PhoneCalibrationPayload | null>(initial.res);
  const [failureReason, setFailureReason] = useState<BuildProfileFailureReason | null>(initial.fail);
  const [isSaved, setIsSaved] = useState(false);
  const [syncedAt, setSyncedAt] = useState<number | null>(null);

  const openCollectorRef = useRef<PhaseCollector | null>(null);
  const closedCollectorRef = useRef<PhaseCollector | null>(null);
  const phaseStartRef = useRef<number>(0);
  const stableStartRef = useRef<number | null>(null);

  // Subscribe to face samples
  useEffect(() => {
    if (override) return;

    return subscribe((sample: FaceSample) => {
      const currentTime = nowRef.current();
      if (step === 'framing') {
        const status = framingStatus(sample);
        setFraming(status);
        const allOk = status.faceInOval && status.lightOk && status.headStraight;

        if (allOk) {
          if (stableStartRef.current === null) {
            stableStartRef.current = currentTime;
            setIsStable(true);
          } else if (currentTime - stableStartRef.current >= 1000) {
            stableStartRef.current = null;
            setIsStable(false);
            setSecondsRemaining(10);
            setStep('open');
          }
        } else {
          stableStartRef.current = null;
          setIsStable(false);
        }
      } else if (step === 'open' && openCollectorRef.current) {
        const elapsed = currentTime - phaseStartRef.current;
        openCollectorRef.current.push({ ...sample, t: elapsed });
      } else if (step === 'closed' && closedCollectorRef.current) {
        const elapsed = currentTime - phaseStartRef.current;
        closedCollectorRef.current.push({ ...sample, t: elapsed });
      }
    });
  }, [step, subscribe, override]);

  // Phase timers and audio/haptics cues
  useEffect(() => {
    if (override) return;

    if (step === 'open') {
      openCollectorRef.current = new PhaseCollector(SETTLE_MS);
      phaseStartRef.current = nowRef.current();
      safeSpeak('cal.eye.voice.open');
      safeHaptic('impact');

      const interval = setInterval(() => {
        const elapsed = Math.floor((nowRef.current() - phaseStartRef.current) / 1000);
        const rem = Math.max(0, 10 - elapsed);
        setSecondsRemaining(rem);
        if (rem <= 0) {
          clearInterval(interval);
          setSecondsRemaining(3);
          setStep('closed');
        }
      }, 250);

      return () => clearInterval(interval);
    }

    if (step === 'closed') {
      // Deliberate difference from Python: closed phase is only 3 s (vs longer in Python)
      // so settle is 0 ms to retain all samples; median is robust against transition noise.
      closedCollectorRef.current = new PhaseCollector(0);
      phaseStartRef.current = nowRef.current();
      safeSpeak('cal.eye.voice.closed');
      safeHaptic('impact');

      const interval = setInterval(() => {
        const elapsed = Math.floor((nowRef.current() - phaseStartRef.current) / 1000);
        const rem = Math.max(0, 3 - elapsed);
        setSecondsRemaining(rem);
        if (rem <= 0) {
          clearInterval(interval);
          safeSpeak('cal.eye.voice.done');
          safeHaptic('success');

          const openCol = openCollectorRef.current ?? new PhaseCollector(SETTLE_MS);
          const closedCol = closedCollectorRef.current ?? new PhaseCollector(0);
          const res = buildProfile(openCol, closedCol);

          if (res.ok) {
            setResultPayload(res.payload);
            setStep('result');
          } else {
            setFailureReason(res.reason);
            setStep('failed');
          }
        }
      }, 250);

      return () => clearInterval(interval);
    }
  }, [step, override]);

  const start = useCallback(() => {
    setFraming(DEFAULT_FRAMING);
    setIsStable(false);
    stableStartRef.current = null;
    setStep('framing');
  }, []);

  const cancel = useCallback(() => {
    stableStartRef.current = null;
    setIsStable(false);
    setStep('intro');
  }, []);

  const retry = useCallback(() => {
    openCollectorRef.current = null;
    closedCollectorRef.current = null;
    stableStartRef.current = null;
    setResultPayload(null);
    setFailureReason(null);
    setIsSaved(false);
    setSyncedAt(null);
    setIsStable(false);
    setFraming(DEFAULT_FRAMING);
    setStep('framing');
  }, []);

  const save = useCallback(() => {
    if (!resultPayload || resultPayload.quality === 'poor') return;
    const at = nowRef.current();

    useSettings.getState().setEyeCalibration({
      closedRatio: resultPayload.closed_ratio,
      earOpen: resultPayload.ear_open,
      earClosed: resultPayload.ear_closed,
      snr: resultPayload.snr,
      quality: resultPayload.quality,
      at,
      syncedAt: null,
      samplesOpen: resultPayload.samples_open,
      samplesClosed: resultPayload.samples_closed,
    });

    setIsSaved(true);
    setSyncedAt(null);

    const isDemo = useSettings.getState().demo;
    if (isDemo) {
      return;
    }

    void syncEyeCalibration(transport).then((res) => {
      if (res === 'ok' && !useSettings.getState().demo) {
        const updated = useSettings.getState().eyeCalibration;
        setSyncedAt(updated?.syncedAt ?? at);
      }
    });
  }, [resultPayload, transport]);

  return {
    step,
    framing,
    isStable,
    secondsRemaining,
    resultPayload,
    failureReason,
    isSaved,
    isSynced: syncedAt !== null,
    start,
    cancel,
    retry,
    save,
  };
}
