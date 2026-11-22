import { useKeepAwake } from 'expo-keep-awake';
import { View } from 'react-native';

import { Button } from '@/components/button';
import { Icon } from '@/components/icon';
import { Row, Section } from '@/components/list';
import { Screen } from '@/components/screen';
import { Text } from '@/components/text';
import { useT } from '@/i18n';
import { radius, spacing, useTheme } from '@/theme';

import { CameraStage } from './camera-stage';
import { CountdownRing } from './countdown-ring';
import { FailureStep } from './failure-step';
import { IntroStep } from './intro-step';
import { ResultStep } from './result-step';
import { useCalibrationMachine, type UseCalibrationMachineReturn } from './use-calibration-machine';
import { useFaceSamples } from './use-face-samples';

function CapturingStage({
  step,
  face,
  machine,
}: {
  step: 'framing' | 'open' | 'closed';
  face: ReturnType<typeof useFaceSamples>;
  machine: UseCalibrationMachineReturn;
}) {
  const t = useT();
  const { colors } = useTheme();
  const isFraming = step === 'framing';
  const isOpen = step === 'open';

  return (
    <View
      style={
        isFraming
          ? { flex: 1, justifyContent: 'space-between', gap: spacing.lg }
          : { flex: 1, justifyContent: 'center', alignItems: 'center', gap: spacing.xxl }
      }
    >
      <View style={isFraming ? { gap: spacing.md } : { gap: spacing.sm, alignItems: 'center' }}>
        {isFraming ? (
          <Text variant="headline" align="center">
            {t('cal.eye.framing.title')}
          </Text>
        ) : (
          <>
            <Text variant="title" align="center">
              {isOpen ? t('cal.eye.open.title') : t('cal.eye.closed.title')}
            </Text>
            <Text variant="body" tone="secondary" align="center">
              {isOpen ? t('cal.eye.open.subtitle') : t('cal.eye.closed.subtitle')}
            </Text>
          </>
        )}

        <View
          style={
            isFraming
              ? {
                  height: 280,
                  width: '100%',
                  borderRadius: radius.lg,
                  borderCurve: 'continuous',
                  backgroundColor: colors.surface,
                  overflow: 'hidden',
                  justifyContent: 'center',
                  alignItems: 'center',
                }
              : {
                  position: 'absolute',
                  width: 1,
                  height: 1,
                  opacity: 0,
                  overflow: 'hidden',
                }
          }
        >
          <CameraStage isNative={face.isNative} onFace={face.onFace} hidden={!isFraming} />

          {isFraming && !face.isNative ? (
            <View style={{ alignItems: 'center', gap: spacing.sm }}>
              <Icon name="camera" size={36} color={colors.textTertiary} />
            </View>
          ) : null}

          {isFraming ? (
            <View
              pointerEvents="none"
              style={{
                position: 'absolute',
                width: 180,
                height: 240,
                borderRadius: 90,
                borderWidth: 3,
                borderStyle: machine.isStable ? 'solid' : 'dashed',
                borderColor: machine.isStable ? colors.alert.none : colors.textSecondary,
                backgroundColor: 'transparent',
              }}
            />
          ) : null}
        </View>

        {isFraming ? (
          <>
            <Section>
              <Row
                icon={machine.framing.faceInOval ? 'check' : 'close'}
                iconColor={machine.framing.faceInOval ? colors.alert.none : colors.textTertiary}
                label={t('cal.eye.framing.face')}
              />
              <Row
                icon={machine.framing.lightOk ? 'check' : 'close'}
                iconColor={machine.framing.lightOk ? colors.alert.none : colors.textTertiary}
                label={t('cal.eye.framing.light')}
              />
              <Row
                icon={machine.framing.headStraight ? 'check' : 'close'}
                iconColor={machine.framing.headStraight ? colors.alert.none : colors.textTertiary}
                label={t('cal.eye.framing.head')}
              />
            </Section>

            {machine.isStable ? (
              <Text variant="caption" tone="secondary" align="center">
                {t('cal.eye.framing.hold')}
              </Text>
            ) : null}
          </>
        ) : null}
      </View>

      {!isFraming ? (
        <CountdownRing
          seconds={machine.secondsRemaining}
          totalSeconds={isOpen ? 10 : 3}
          running
        />
      ) : null}

      {isFraming ? (
        <Button title={t('cal.eye.cancel')} variant="ghost" size="md" onPress={machine.cancel} />
      ) : null}
    </View>
  );
}

export function EyeCalibrationScreen({
  isOnboarding,
  onDone,
}: {
  isOnboarding?: boolean;
  onDone: () => void;
}) {
  useKeepAwake(undefined, { suppressDeactivateWarnings: true }); // Android rejects deactivate once the activity is gone
  const face = useFaceSamples();
  const machine = useCalibrationMachine({ subscribe: face.subscribe });

  const isCapturing =
    machine.step === 'framing' ||
    machine.step === 'open' ||
    machine.step === 'closed';

  return (
    <Screen contentContainerStyle={{ flexGrow: 1, justifyContent: 'space-between' }}>
      {machine.step === 'intro' ? (
        <IntroStep
          isOnboarding={isOnboarding}
          onStart={machine.start}
          onLater={onDone}
        />
      ) : null}

      {isCapturing ? (
        <CapturingStage
          step={machine.step as 'framing' | 'open' | 'closed'}
          face={face}
          machine={machine}
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
          onCancel={onDone}
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
