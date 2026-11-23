/**
 * Wire types for the Pi HTTP API. `PiStatus` mirrors `models/distraction/scripts/stream.py`
 * (`pipeline_loop` → `status` dict, `drowsiness.py` `Drowsiness.feed`, `hybrid.py` `Hybrid.feed`)
 * field for field. Alert and physio follow `contracts/pi-link/` v1.3.
 *
 * Type-only module with erasable syntax: the mock Pi server runs it under Node type stripping.
 */

/** fusion/src/dms_fusion AlertPattern, in fusion's order (index = severity). */
export const ALERT_PATTERNS = ['none', 'short_beep', 'repeated', 'continuous', 'max'] as const;
export type AlertPattern = (typeof ALERT_PATTERNS)[number];

/** dms_face DriverState values, plus "starting" (drowsiness.py before the first report). */
export type DrowsinessState =
  | 'starting'
  | 'unavailable'
  | 'alert'
  | 'distracted'
  | 'warning'
  | 'drowsy';

/** stream.py `--drowsiness`: models/distraction/scripts/drowsiness.py `Drowsiness.feed`. */
export type PiDrowsiness = {
  state: DrowsinessState;
  reasons: string[];
  perclos: number | null;
  perclos_valid: boolean;
  blink_rate: number | null;
  closure_ms: number;
  /** Calibrated, smoothed eye openness (not the raw eye aspect ratio). */
  openness: number | null;
  face: boolean;
  calibrated: boolean;
  calibration: 'ok' | 'calibrating' | 'failed' | 'lost' | null;
  message: string;
  ms: number;
};

/** stream.py `--hybrid`: hybrid.py `Hybrid.feed` minus `onsets` and `ms`. */
export type PiHybrid = {
  face: boolean;
  call: boolean;
  texting: boolean;
  action: string | null;
  p: number | null;
  /** Phone-at-ear probability (NOT the eye aspect ratio). */
  ear: number | null;
  /** Phone-in-lap probability. */
  lap: number | null;
};

/** Release-rule behaviour level (configs/rules.yaml `levels`). */
export type BehaviourLevel = 'none' | 'warning' | 'alert';

/** GET /status, exactly as stream.py serves it. Optional keys depend on stream.py flags. */
export type PiStatus = PayloadTime & {
  fps: number;
  face: boolean;
  baseline: number;
  levels: Record<string, BehaviourLevel>;
  ms: Record<string, number>;
  /** Absent until the first frame is processed. */
  temp_c?: number | null;
  drowsiness?: PiDrowsiness;
  hybrid?: PiHybrid;
};

/** Shared optional source metadata; status time may be absent on older units. */
export type PayloadTime = { t?: number; t_src?: 'phone' | 'pi' };
export type PiAlert = PayloadTime & { pattern: AlertPattern; reasons: string[]; t: number; emergency?: 'unresponsive' };

/** physiology HrvSnapshot.state / QualityState (models/physiology garmin_hrv.py, types.py). */
export type HrvState = 'warmup' | 'valid' | 'degraded' | 'bad' | 'stale';
export type SignalQuality = 'good' | 'degraded' | 'bad';

/** Physio v2: HR context plus PRV/RR fields used only in Diagnostics. */
export type PiPhysio = {
  watch_connected: boolean;
  hr_bpm: number | null;
  rr_ms: number[];
  worn: boolean | null;
  hr_baseline_bpm: number | null;
  hr_delta_bpm: number | null;
  hr_trend_bpm_per_10min: number | null;
  quality: SignalQuality | null;
  hrv_state: HrvState | null;
  rmssd_ms: number | null;
  t_src?: 'phone' | 'pi';
  t: number;
};

export type ModelState = 'running' | 'off' | 'error';

/** GET /health (proposed). `throttled` is the raw `vcgencmd get_throttled` bitmask. */
export type PiHealth = {
  physio_diag?: Partial<Record<'watch_offset_spread_ms' | 'late_packets' | 'shadow_agree' | 'shadow_disagree' | 'shadow_only', number | null>>;
  cpu_pct: number;
  temp_c: number | null;
  throttled: number;
  volts_5v: number | null;
  fps: number;
  uptime_s: number;
  mem_used_mb: number;
  mem_total_mb: number;
  disk_free_mb: number;
  disk_total_mb: number;
  camera: 'ok' | 'lost';
  models: Record<string, ModelState>;
};

export type Sensitivity = 'low' | 'normal' | 'high';

/** GET / PUT /settings (proposed). Thresholds live on the Pi: fusion applies them. */
export type PiSettings = {
  profile: string;
  profiles: string[];
  sensitivity: Sensitivity;
  eye_closure_s: number;
  offroad_gaze_s: number;
  phone_s: number;
  detectors: Record<'drowsiness' | 'distraction' | 'phone' | 'physiology', boolean>;
};

/** POST /incident body (proposed). */
export type IncidentRequest = {
  t_crash: number;
  g_peak: number;
  lat: number | null;
  lon: number | null;
};

/** GET /incidents item (proposed). */
export type PiIncident = {
  id: string;
  t_crash: number;
  g_peak: number;
  lat: number | null;
  lon: number | null;
  duration_s: number;
  clip_ready: boolean;
};

/** One line of /incidents/<id>/data.jsonl (proposed): per-frame status from the ring buffer. */
export type IncidentFrame = { t: number; status: PiStatus; alert?: PiAlert };
