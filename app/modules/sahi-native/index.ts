// On web this resolves to SahiNativeModule.web.ts (null); on Android to the native module.
export { default } from './src/SahiNativeModule';
export * from './src/SahiNative.types';
export { SahiFaceView, isFaceViewAvailable } from './src/SahiFaceView';
export {
  createFakeFaceSource,
  type FakeScript,
  type FakeFaceSourceOptions,
  type FakeFaceSource,
} from './src/FakeFaceSource';
