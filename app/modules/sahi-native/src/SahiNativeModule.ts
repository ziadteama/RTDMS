import { NativeModule, requireOptionalNativeModule } from 'expo';

import type { NotifyChannel, SahiNativeModuleEvents } from './SahiNative.types';

declare class SahiNativeModule extends NativeModule<SahiNativeModuleEvents> {
  hasTelephony(): boolean;
  sendSms(numbers: string[], text: string): Promise<number>;
  call(number: string): Promise<void>;
  notify(id: number, channel: NotifyChannel, title: string, body: string, url: string | null): void;
  cancel(id: number): void;
  startMotion(hz: number): void;
  stopMotion(): void;
  joinWifi(ssid: string, password: string): Promise<boolean>;
  unbindNetwork(): void;
}

/** null outside an Android development build (Expo Go, iOS, web, Jest). */
export default requireOptionalNativeModule<SahiNativeModule>('SahiNative');
