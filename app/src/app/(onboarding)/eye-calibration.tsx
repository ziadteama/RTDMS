import { router } from 'expo-router';

import { EyeCalibrationScreen } from '@/screens/calibration';

export default function OnboardingEyeCalibrationRoute() {
  return (
    <EyeCalibrationScreen
      isOnboarding
      onDone={() => router.push('/emergency-contacts')}
    />
  );
}
