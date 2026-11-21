import { Redirect } from 'expo-router';

import { useSettings } from '@/state/settings';

export default function Index() {
  const onboarded = useSettings((s) => s.onboarded);
  return <Redirect href={onboarded ? '/live' : '/consent'} />;
}
