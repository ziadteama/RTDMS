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
    </Screen>
  );
}
