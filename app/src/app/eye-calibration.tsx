import { router } from 'expo-router';

import { EyeCalibrationScreen } from '@/screens/calibration';

export default function EyeCalibrationRoute() {
  return <EyeCalibrationScreen onDone={() => router.back()} />;
}
