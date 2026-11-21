export type MotionEvent = {
  /** Flattened [t_ms, ax, ay, az, gx, gy, gz] * n. Accel in m/s² (gravity included), gyro in rad/s. */
  samples: number[];
};

export type SahiNativeModuleEvents = {
  onMotion: (e: MotionEvent) => void;
};

export type NotifyChannel = 'alerts' | 'sos';
