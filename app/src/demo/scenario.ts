/**
 * A deterministic, synthetic two-minute drive that exercises every driver state the Pi reports.
 * Used by both the mock Pi server (`mock-pi/server.ts`, over HTTP) and the in-app demo mode
 * (no network), so the two never drift apart.
 *
 * The alert pattern per phase is SCRIPTED to match what `fusion/src/dms_fusion` `decide()` returns
 * for those inputs. It stands in for the Pi; the app never derives a pattern from scores itself.
 *
 * Erasable TypeScript only (no enums, type-only imports): Node runs this file directly.
 */
import type {
  AlertPattern,
  IncidentFrame,
  DrowsinessState,
  PiAlert,
  PiHealth,
  PiPhysio,
  PiStatus,
  SignalQuality,
} from '../pi/types.ts';

export const SCENARIO_LENGTH_S = 120;

type Phase = {
  until: number;
  name: string;
  state: DrowsinessState;
  reasons: string[];
  call?: boolean;
  texting?: boolean;
  face?: boolean;
  perclos: number;
  openness: number;
  closureMs: number;
  hr: number;
  fatigue: number;
  quality: SignalQuality;
  pattern: AlertPattern;
  alertReasons: string[];
  speedKmh: number;
};

const PHASES: Phase[] = [
  { until: 20, name: 'normal', state: 'alert', reasons: [], perclos: 0.04, openness: 0.86, closureMs: 0, hr: 76, fatigue: 0.18, quality: 'good', pattern: 'none', alertReasons: [], speedKmh: 0 },
  { until: 30, name: 'distracted', state: 'distracted', reasons: ['gaze off road'], perclos: 0.05, openness: 0.8, closureMs: 0, hr: 78, fatigue: 0.2, quality: 'good', pattern: 'short_beep', alertReasons: ['face distracted'], speedKmh: 55 },
  { until: 40, name: 'normal', state: 'alert', reasons: [], perclos: 0.05, openness: 0.84, closureMs: 0, hr: 77, fatigue: 0.2, quality: 'good', pattern: 'none', alertReasons: [], speedKmh: 62 },
  { until: 52, name: 'call', state: 'alert', reasons: [], call: true, perclos: 0.05, openness: 0.83, closureMs: 0, hr: 82, fatigue: 0.22, quality: 'good', pattern: 'continuous', alertReasons: ['phone sustained'], speedKmh: 64 },
  { until: 62, name: 'normal', state: 'alert', reasons: [], perclos: 0.06, openness: 0.82, closureMs: 0, hr: 78, fatigue: 0.25, quality: 'good', pattern: 'none', alertReasons: [], speedKmh: 70 },
  { until: 75, name: 'texting', state: 'distracted', reasons: ['head down'], texting: true, perclos: 0.07, openness: 0.7, closureMs: 0, hr: 80, fatigue: 0.27, quality: 'degraded', pattern: 'continuous', alertReasons: ['phone sustained', 'face distracted'], speedKmh: 48 },
  { until: 85, name: 'warning', state: 'warning', reasons: ['perclos rising'], perclos: 0.17, openness: 0.58, closureMs: 600, hr: 70, fatigue: 0.45, quality: 'good', pattern: 'none', alertReasons: [], speedKmh: 66 },
  { until: 100, name: 'drowsy', state: 'drowsy', reasons: ['perclos high', 'long eye closure'], perclos: 0.31, openness: 0.34, closureMs: 2400, hr: 66, fatigue: 0.62, quality: 'good', pattern: 'repeated', alertReasons: ['face drowsy'], speedKmh: 72 },
  { until: 110, name: 'drowsy+physio', state: 'drowsy', reasons: ['perclos high', 'long eye closure'], perclos: 0.36, openness: 0.29, closureMs: 3100, hr: 64, fatigue: 0.78, quality: 'good', pattern: 'max', alertReasons: ['face drowsy', 'physio confirms'], speedKmh: 74 },
  { until: 120, name: 'face lost', state: 'unavailable', reasons: ['no face'], face: false, perclos: 0.3, openness: 0, closureMs: 0, hr: 70, fatigue: 0.6, quality: 'bad', pattern: 'none', alertReasons: [], speedKmh: 30 },
];

/** Cheap deterministic jitter in [-1, 1]. */
function wobble(t: number, k: number): number {
  return Math.sin(t * 1.7 + k) * 0.6 + Math.sin(t * 4.3 + k * 2) * 0.4;
}

const round = (v: number, d: number) => Math.round(v * 10 ** d) / 10 ** d;

export function phaseAt(t: number): Phase {
  const s = ((t % SCENARIO_LENGTH_S) + SCENARIO_LENGTH_S) % SCENARIO_LENGTH_S;
  return PHASES.find((p) => s < p.until) ?? PHASES[PHASES.length - 1]!;
}

/** GET /status for a Pi started as `stream.py --drowsiness --hybrid --no-detect` (the v2 setup). */
export function statusAt(t: number, calibration?: { message: string; calibrated: boolean }): PiStatus {
  const p = phaseAt(t);
  const face = p.face !== false;
  const fps = round(14.6 + wobble(t, 1) * 0.6, 1);
  const msDrowsy = round(6.2 + wobble(t, 2) * 0.8, 1);
  return {
    fps,
    face,
    baseline: Math.min(1, t / 20),
    levels: {},
    ms: {
      capture: round(1.1 + wobble(t, 3) * 0.2, 1),
      facemesh: round(18.4 + wobble(t, 4) * 2, 1),
      drowsiness: msDrowsy,
      v2_phone: round(21.7 + wobble(t, 5) * 2.5, 1),
    },
    temp_c: round(63 + (t % SCENARIO_LENGTH_S) / 30 + wobble(t, 6) * 0.4, 1),
    drowsiness: {
      state: p.state,
      reasons: p.reasons,
      perclos: face ? round(p.perclos + wobble(t, 7) * 0.01, 3) : null,
      perclos_valid: t > 60 || p.perclos > 0.1,
      blink_rate: face ? round(16 - p.perclos * 20 + wobble(t, 8), 1) : null,
      closure_ms: Math.max(0, Math.round(p.closureMs + wobble(t, 9) * 200 * (p.closureMs > 0 ? 1 : 0))),
      openness: face ? round(Math.max(0, p.openness + wobble(t, 10) * 0.04), 2) : null,
      face,
      calibrated: calibration?.calibrated ?? true,
      message: calibration?.message ?? 'calibrated',
      ms: msDrowsy,
    },
    hybrid: {
      face,
      call: p.call === true,
      texting: p.texting === true,
      action: !face ? null : p.call ? 'call' : p.texting ? 'texting' : 'drive',
      p: face ? round(0.86 + wobble(t, 11) * 0.06, 2) : null,
      ear: face ? round(p.call ? 0.9 : 0.04 + Math.abs(wobble(t, 12)) * 0.03, 2) : null,
      lap: face ? round(p.texting ? 0.82 : 0.05 + Math.abs(wobble(t, 13)) * 0.03, 2) : null,
    },
  };
}

export function alertAt(t: number): PiAlert {
  const p = phaseAt(t);
  return { pattern: p.pattern, reasons: p.alertReasons, t: round(t, 2) };
}

export function physioAt(t: number): PiPhysio {
  const p = phaseAt(t);
  const hr = Math.round(p.hr + wobble(t, 14) * 2);
  const watch = p.quality !== 'bad';
  return {
    watch_connected: watch,
    hr_bpm: watch ? hr : null,
    rr_ms: watch ? [Math.round(60000 / hr + wobble(t, 15) * 20), Math.round(60000 / hr + wobble(t, 16) * 20)] : [],
    fatigue_probability: watch && t > 60 ? round(p.fatigue + wobble(t, 17) * 0.02, 2) : null,
    hrv: watch
      ? {
          state: t < 60 ? 'warmup' : p.quality === 'good' ? 'valid' : 'degraded',
          mean_hr_bpm: round(p.hr + wobble(t, 18), 1),
          rmssd_ms: t < 60 ? null : round(38 - p.fatigue * 10 + wobble(t, 19) * 3, 1),
          quality: p.quality,
          coverage: p.quality === 'good' ? 0.94 : 0.71,
        }
      : null,
    t: round(t, 2),
  };
}

export function healthAt(t: number, uptimeS: number): PiHealth {
  const s = statusAt(t);
  return {
    cpu_pct: round(61 + wobble(t, 20) * 6, 1),
    temp_c: s.temp_c ?? null,
    throttled: 0,
    volts_5v: round(5.08 + wobble(t, 21) * 0.03, 2),
    fps: s.fps,
    uptime_s: Math.round(uptimeS),
    mem_used_mb: Math.round(2140 + wobble(t, 22) * 40),
    mem_total_mb: 8064,
    disk_free_mb: 41210,
    disk_total_mb: 58940,
    camera: 'ok',
    models: { face: 'running', distraction: 'running', physiology: 'running', fusion: 'running' },
  };
}

/** Faked GPS speed for demo mode (the real speed comes from the phone's GPS). */
export function speedAt(t: number): number {
  return phaseAt(t).speedKmh;
}

/**
 * Per-frame data for an incident, like the planned Pi ring buffer: 15 s before + 10 s after the
 * crash at 10 fps. `tScenario` is where in the scenario the crash happened.
 */
export function incidentFrames(tScenario: number, tCrashMs: number): IncidentFrame[] {
  const frames: IncidentFrame[] = [];
  for (let k = -150; k < 100; k++) {
    const t = tScenario + k / 10;
    const s = statusAt(((t % SCENARIO_LENGTH_S) + SCENARIO_LENGTH_S) % SCENARIO_LENGTH_S);
    if (k >= 0 && k < 30) {
      // after the impact the face is lost for 3 s
      s.face = false;
      if (s.drowsiness) s.drowsiness = { ...s.drowsiness, state: 'unavailable', face: false, openness: null };
      if (s.hybrid) s.hybrid = { ...s.hybrid, face: false };
    }
    frames.push({ t: tCrashMs + k * 100, status: s, alert: alertAt(t) });
  }
  return frames;
}
