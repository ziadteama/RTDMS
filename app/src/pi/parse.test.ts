import { statusAt } from '@/demo/scenario';

import {
  decodeThrottled,
  normalizeBaseUrl,
  parseAlert,
  parseHealth,
  parseIncidents,
  parsePhysio,
  parseQr,
  parseSettings,
  parseStatus,
} from './parse';

// Copied from models/distraction/scripts/stream.py: Shared.status before the first frame.
const INITIAL = { fps: 0, face: false, baseline: 0, levels: {}, ms: {} };

// What stream.py --drowsiness --hybrid --no-detect serves (keys from pipeline_loop,
// drowsiness.py Drowsiness.feed and hybrid.py Hybrid.feed).
const V2 = {
  fps: 14.3,
  face: true,
  baseline: 1,
  levels: {},
  ms: { capture: 1.2, facemesh: 18.9, drowsiness: 6.1, v2_phone: 22.4 },
  temp_c: 64.2,
  drowsiness: {
    state: 'drowsy',
    reasons: ['perclos high'],
    perclos: 0.312,
    perclos_valid: true,
    blink_rate: 9.5,
    closure_ms: 2400,
    openness: 0.31,
    face: true,
    calibrated: true,
    message: 'calibrated',
    ms: 6.1,
  },
  hybrid: { face: true, call: false, texting: true, action: 'texting', p: 0.91, ear: 0.03, lap: 0.84 },
};

// stream.py without --no-detect: release box rules report per-behaviour levels.
const V1 = {
  fps: 9.8,
  face: true,
  baseline: 0.4,
  levels: { phone_right_ear: 'alert', drinking: 'none' },
  ms: { detect: 41.2, facemesh: 17.3 },
  temp_c: null,
};

describe('parseStatus', () => {
  it('accepts the initial status (no temp_c yet)', () => {
    expect(parseStatus(INITIAL)).toEqual(INITIAL);
  });

  it('round-trips the full v2 status exactly', () => {
    expect(parseStatus(V2)).toEqual(V2);
  });

  it('accepts v1 levels and a null temperature', () => {
    expect(parseStatus(V1)).toEqual(V1);
  });

  it('round-trips every second of the demo scenario (mock Pi = real shape)', () => {
    for (let t = 0; t < 120; t += 0.5) {
      const s = statusAt(t);
      expect(parseStatus(JSON.parse(JSON.stringify(s)))).toEqual(s);
    }
  });

  it('rejects garbage without guessing', () => {
    expect(parseStatus(null)).toBeNull();
    expect(parseStatus('ok')).toBeNull();
    expect(parseStatus({ face: true })).toBeNull();
    expect(parseStatus({ fps: 'fast', face: true })).toBeNull();
  });

  it('drops bad fields instead of inventing values', () => {
    const s = parseStatus({
      ...V2,
      levels: { phone_in_hand: 'panic', eating: 'warning' },
      ms: { capture: 'n/a', facemesh: 12 },
      drowsiness: { ...V2.drowsiness, state: 'sleepwalking', perclos: 'high', openness: null },
    });
    expect(s!.levels).toEqual({ eating: 'warning' });
    expect(s!.ms).toEqual({ facemesh: 12 });
    expect(s!.drowsiness!.state).toBe('unavailable');
    expect(s!.drowsiness!.perclos).toBeNull();
    expect(s!.drowsiness!.openness).toBeNull();
  });
});

describe('other endpoints', () => {
  it('parses /alert and rejects unknown patterns', () => {
    expect(parseAlert({ pattern: 'max', reasons: ['face drowsy', 'physio confirms'], t: 3 })).toEqual({
      pattern: 'max',
      reasons: ['face drowsy', 'physio confirms'],
      t: 3,
    });
    expect(parseAlert({ pattern: 'LOUD' })).toBeNull();
  });

  it('parses /physio and nulls an out-of-range probability', () => {
    const p = parsePhysio({
      watch_connected: true,
      hr_bpm: 71,
      rr_ms: [845, 'x', 850],
      fatigue_probability: 1.7,
      hrv: { state: 'valid', mean_hr_bpm: 70.2, rmssd_ms: 35.1, quality: 'good', coverage: 0.93 },
      t: 5,
    });
    expect(p!.rr_ms).toEqual([845, 850]);
    expect(p!.fatigue_probability).toBeNull();
    expect(p!.hrv!.quality).toBe('good');
  });

  it('parses /health; unknown model state is an error, not running', () => {
    const h = parseHealth({ cpu_pct: 55, throttled: 0x50005, camera: 'ok', models: { face: 'running', phone: 'zzz' } });
    expect(h!.models).toEqual({ face: 'running', phone: 'error' });
    expect(decodeThrottled(h!.throttled)).toMatchObject({
      underVoltageNow: true,
      throttledNow: true,
      underVoltageOccurred: true,
      throttledOccurred: true,
      freqCappedNow: false,
    });
  });

  it('parses /settings and refuses a partial one', () => {
    const ok = {
      profile: 'default',
      profiles: ['default'],
      sensitivity: 'normal',
      eye_closure_s: 2,
      offroad_gaze_s: 2,
      phone_s: 1,
      detectors: { drowsiness: true, distraction: true, phone: false, physiology: true },
    };
    expect(parseSettings(ok)).toEqual(ok);
    expect(parseSettings({ ...ok, eye_closure_s: undefined })).toBeNull();
  });

  it('parses /incidents and skips broken items', () => {
    expect(parseIncidents([{ id: 'a', t_crash: 1, g_peak: 6 }, { id: 3 }, 'x'])).toHaveLength(1);
  });
});

describe('pairing', () => {
  const DEF = 'http://10.42.0.1:8080';
  it('reads the Pi QR (Wi-Fi + base URL, escaped chars)', () => {
    expect(parseQr(String.raw`WIFI:T:WPA;S:RTDMS-Pi;P:se\;cret;U:http://10.42.0.1:8080/;;`, DEF)).toEqual({
      ssid: 'RTDMS-Pi',
      password: 'se;cret',
      baseUrl: 'http://10.42.0.1:8080',
    });
  });
  it('falls back to the default base URL for a plain Wi-Fi QR', () => {
    expect(parseQr('WIFI:S:car;T:nopass;;', DEF)).toEqual({ ssid: 'car', password: null, baseUrl: DEF });
  });
  it('accepts a bare URL and rejects other QR codes', () => {
    expect(parseQr('http://192.168.1.20:8080', DEF)!.baseUrl).toBe('http://192.168.1.20:8080');
    expect(parseQr('https://example.com/menu pdf', DEF)).toBeNull();
    expect(parseQr('hello', DEF)).toBeNull();
  });
  it('normalizes a typed address', () => {
    expect(normalizeBaseUrl(' 192.168.1.20:8080/ ')).toBe('http://192.168.1.20:8080');
    expect(normalizeBaseUrl('')).toBeNull();
    expect(normalizeBaseUrl('not a url')).toBeNull();
  });
});
