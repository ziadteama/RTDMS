export type MotionEvent = {
  /** Flattened [t_ms, ax, ay, az, gx, gy, gz] * n. Accel in m/s² (gravity included), gyro in rad/s. */
  samples: number[];
};

export type SmsStatusEvent = {
  phone: string;
  status: 'sent' | 'delivered' | 'failed';
};

export type SahiNativeModuleEvents = {
  onMotion: (e: MotionEvent) => void;
  onSmsStatus: (e: SmsStatusEvent) => void;
};

export type NotifyChannel = 'alerts' | 'sos';

export type FaceSample = {
  faceFound: boolean;
  ear: number | null;
  earLeft: number | null;
  earRight: number | null;
  earValid: boolean;
  yaw: number | null;
  pitch: number | null;
  faceBoxFraction: number;
  luma: number;
  t: number;
};
