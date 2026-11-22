import { useKeepAwake } from 'expo-keep-awake';

import { Screen } from '@/components/screen';

import { FailureStep } from './failure-step';
import { FramingStep } from './framing-step';
import { IntroStep } from './intro-step';
import { MeasureStep } from './measure-step';
import { ResultStep } from './result-step';
import { useCalibrationMachine } from './use-calibration-machine';
import { useFaceSamples } from './use-face-samples';

export function EyeCalibrationScreen({
  isOnboarding,
  onDone,
}: {
  isOnboarding?: boolean;
  onDone: () => void;
}) {
  useKeepAwake();
  const face = useFaceSamples();
  const machine = useCalibrationMachine({ subscribe: face.subscribe });

  return (
    <Screen contentContainerStyle={{ flexGrow: 1, justifyContent: 'space-between' }}>
      {machine.step === 'intro' ? (
        <IntroStep
          isOnboarding={isOnboarding}
          onStart={machine.start}
          onLater={onDone}
        />
      ) : null}

      {machine.step === 'framing' ? (
        <FramingStep
          isNative={face.isNative}
          onFace={face.onFace}
          status={machine.framing}
          isStable={machine.isStable}
          onCancel={machine.cancel}
        />
      ) : null}

      {machine.step === 'open' || machine.step === 'closed' ? (
        <MeasureStep
          phase={machine.step}
          secondsRemaining={machine.secondsRemaining}
          isNative={face.isNative}
          onFace={face.onFace}
        />
      ) : null}

      {machine.step === 'result' ? (
        <ResultStep
          quality={machine.resultPayload?.quality ?? 'good'}
          isSaved={machine.isSaved}
          isSynced={machine.isSynced}
          onSave={machine.save}
          onRetry={machine.retry}
          onDone={onDone}
        />
      ) : null}

      {machine.step === 'failed' ? (
        <FailureStep
          reason={machine.failureReason ?? 'too_few_samples'}
          onRetry={machine.retry}
          onCancel={machine.cancel}
        />
      ) : null}
    </Screen>
  );
}
