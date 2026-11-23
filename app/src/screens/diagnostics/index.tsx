import { router } from 'expo-router';

import { Row, Section } from '@/components/list';
import { dx } from '@/i18n/diagnostics';
import { Screen } from '@/components/screen';

import { ConnectionDiag } from './connection';
import { DetectionTuning } from './detection-tuning';
import { RawMetrics } from './raw-metrics';
import { UnitHealth } from './unit-health';

export function Diagnostics() {
  return (
    <Screen>
      <UnitHealth />
      <DetectionTuning />
      <ConnectionDiag />
      <RawMetrics />
      <Section title={dx('diag.calibration')}>
        <Row label={dx('diag.phoneCalibration')} chevron onPress={() => router.push('/eye-calibration')} />
      </Section>
    </Screen>
  );
}
