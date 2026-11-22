export type EarSample = {
  t: number;
  ear: number | null;
  earValid: boolean;
  faceFound: boolean;
  yaw: number | null;
  pitch: number | null;
  luma: number;
  faceBoxFraction: number;
};

export type CalibrationQuality = 'good' | 'fair' | 'poor';

export type PhoneCalibrationPayload = {
  source: 'phone';
  closed_ratio: number;
  ear_open: number;
  ear_closed: number;
  snr: number;
  quality: CalibrationQuality;
  samples_open: number;
  samples_closed: number;
  created: number;
};

export type BuildProfileFailureReason =
  | 'no_face'
  | 'too_dark'
  | 'head_turned'
  | 'eyes_not_shut'
  | 'too_few_samples';

export type BuildProfileResult =
  | { ok: true; payload: PhoneCalibrationPayload }
  | { ok: false; reason: BuildProfileFailureReason };

export type RejectCounts = {
  noFace: number;
  headTurned: number;
  invalidEar: number;
  total: number;
};

export type PhaseResult = {
  ear: number | null;
  yaw: number | null;
  pitch: number | null;
  meanLuma: number | null;
  n: number;
  noise: number | null;
  mad: number | null;
  rejects: RejectCounts;
  totalSamples: number;
};

export type FramingStatus = {
  faceInOval: boolean;
  lightOk: boolean;
  headStraight: boolean;
};
