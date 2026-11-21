import { Screen } from '@/components/screen';

import { AboutSection } from './about-section';
import { AlertsSection } from './alerts-section';
import { AppSection } from './app-section';
import { EmergencySection } from './emergency-section';
import { PrivacySection } from './privacy-section';
import { UnitSection } from './unit-section';

export function Settings() {
  return (
    <Screen>
      <UnitSection />
      <AlertsSection />
      <EmergencySection />
      <PrivacySection />
      <AppSection />
      <AboutSection />
    </Screen>
  );
}
