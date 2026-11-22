import * as Haptics from 'expo-haptics';
import { Platform } from 'react-native';

import {
  SahiFaceView,
  isFaceViewAvailable,
  createFakeFaceSource,
  type FaceSample,
  type FakeScript,
} from '@modules/sahi-native';
import {
  PhaseCollector,
  buildProfile,
  framingStatus,
  type EarSample,
  type FramingStatus,
  type BuildProfileResult,
  type BuildProfileFailureReason,
  type CalibrationQuality,
  type PhoneCalibrationPayload,
} from '@/calibration';
import type { StringKey } from '@/i18n';
import { speak } from '@/services/alerts';
import { syncEyeCalibration } from '@/services/calibration-sync';
import { useLive } from '@/state/live';
import { useSettings, type EyeCalibration } from '@/state/settings';

const SETTLE_S = 2;

export {
  SahiFaceView,
  isFaceViewAvailable,
  createFakeFaceSource,
  PhaseCollector,
  buildProfile,
  framingStatus,
  SETTLE_S,
  useSettings,
  syncEyeCalibration,
  useLive,
};

export type {
  FaceSample,
  FakeScript,
  EarSample,
  FramingStatus,
  BuildProfileResult,
  BuildProfileFailureReason,
  CalibrationQuality,
  PhoneCalibrationPayload,
  EyeCalibration,
};

export function safeHaptic(style: 'impact' | 'warning' | 'success' = 'impact'): void {
  if (Platform.OS === 'web') return;
  try {
    if (style === 'impact') {
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } else if (style === 'warning') {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    } else if (style === 'success') {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    }
  } catch {
    // Degrade silently on platforms without haptics
  }
}

export function safeSpeak(key: StringKey, params?: Record<string, string | number>): void {
  try {
    speak(key, params);
  } catch {
    // Degrade silently if speech fails
  }
}
