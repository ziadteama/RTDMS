import { router } from 'expo-router';

import { PiCalibrationScreen } from '@/screens/pi-calibration';

export default function OnboardingEyeCalibrationRoute() {
  return (
    <PiCalibrationScreen
      isOnboarding
      onDone={() => router.push('/emergency-contacts')}
    />
  );
}
