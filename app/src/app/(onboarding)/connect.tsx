import { router } from 'expo-router';

import { Screen } from '@/components/screen';
import { Pair } from '@/screens/pair';

export default function Connect() {
  return (
    <Screen>
      <Pair onDone={() => router.push('/eye-calibration')} />
    </Screen>
  );
}
