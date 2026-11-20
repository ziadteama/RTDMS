import { router } from 'expo-router';

import { Screen } from '@/components/screen';
import { Pair } from '@/screens/pair';

export default function PairRoute() {
  return (
    <Screen>
      <Pair onDone={() => router.back()} />
    </Screen>
  );
}
