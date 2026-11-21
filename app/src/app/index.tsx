import { Redirect } from 'expo-router';

// app/scaffold has onboarding only; app/live-view adds the tabs and sends onboarded drivers there.
export default function Index() {
  return <Redirect href="/consent" />;
}
