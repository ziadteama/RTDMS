import { statusAt } from '@/demo/scenario';

import { ALERT_PRESENTATION, driverState, isEscalation, severity, voiceKey } from './alert';
import { ALERT_PATTERNS } from './types';

describe('AlertPattern presentation', () => {
  it('covers every fusion pattern, in fusion order', () => {
    expect(Object.keys(ALERT_PRESENTATION)).toEqual([...ALERT_PATTERNS]);
    expect(ALERT_PATTERNS.map(severity)).toEqual([0, 1, 2, 3, 4]);
  });

  it('never gets quieter as severity rises', () => {
    const rank = { none: 0, tap: 1, warning: 2, error: 3 } as const;
    for (let i = 1; i < ALERT_PATTERNS.length; i++) {
      const a = ALERT_PRESENTATION[ALERT_PATTERNS[i - 1]!];
      const b = ALERT_PRESENTATION[ALERT_PATTERNS[i]!];
      expect(rank[b.haptic]).toBeGreaterThanOrEqual(rank[a.haptic]);
      expect(Number(b.notify)).toBeGreaterThanOrEqual(Number(a.notify));
      if (a.repeatMs && b.repeatMs) expect(b.repeatMs).toBeLessThanOrEqual(a.repeatMs);
    }
    expect(ALERT_PRESENTATION.none).toMatchObject({ notify: false, voice: false, haptic: 'none' });
    expect(ALERT_PRESENTATION.max.pulse).toBe(true);
  });

  it('escalation is a strict rise in severity', () => {
    expect(isEscalation(null, 'short_beep')).toBe(true);
    expect(isEscalation('repeated', 'max')).toBe(true);
    expect(isEscalation('max', 'repeated')).toBe(false);
    expect(isEscalation('none', 'none')).toBe(false);
  });
});

describe('driverState (labels from the Pi categorical outputs)', () => {
  it('offline when not connected, whatever the last status said', () => {
    expect(driverState(statusAt(90), false)).toBe('offline');
    expect(driverState(null, true)).toBe('offline');
  });

  it('follows the scenario phases', () => {
    expect(driverState(statusAt(5), true)).toBe('attentive');
    expect(driverState(statusAt(25), true)).toBe('distracted');
    expect(driverState(statusAt(45), true)).toBe('phone');
    expect(driverState(statusAt(70), true)).toBe('phone'); // texting wins over head-down
    expect(driverState(statusAt(80), true)).toBe('warning');
    expect(driverState(statusAt(90), true)).toBe('drowsy');
    expect(driverState(statusAt(115), true)).toBe('noFace');
  });

  it('uses v1 behaviour levels when drowsiness is not running', () => {
    expect(driverState({ fps: 9, face: true, baseline: 1, levels: { drinking: 'warning' }, ms: {} }, true)).toBe('distracted');
    expect(driverState({ fps: 9, face: false, baseline: 1, levels: {}, ms: {} }, true)).toBe('noFace');
  });

  it('picks a voice line that names what to do', () => {
    expect(voiceKey('none', 'drowsy')).toBeNull();
    expect(voiceKey('continuous', 'phone')).toBe('voice.phone');
    expect(voiceKey('repeated', 'drowsy')).toBe('voice.drowsy');
    expect(voiceKey('max', 'drowsy')).toBe('voice.max');
    expect(voiceKey('short_beep', 'distracted')).toBe('voice.distracted');
  });
});
