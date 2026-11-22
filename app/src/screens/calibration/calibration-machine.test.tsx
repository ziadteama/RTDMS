import { act, render } from '@testing-library/react-native';
import React from 'react';

import { createFakeFaceSource, type FaceSample } from './adapters';
import {
  useCalibrationMachine,
  type UseCalibrationMachineOptions,
  type UseCalibrationMachineReturn,
} from './use-calibration-machine';
import { useLive } from '@/state/live';
import { useSettings } from '@/state/settings';
import * as alerts from '@/services/alerts';
import * as sync from '@/services/calibration-sync';

const mockStore = new Map<string, string>();
jest.mock('expo-sqlite/kv-store', () => ({
  Storage: {
    getItemSync: jest.fn((k: string) => mockStore.get(k) ?? null),
    setItemSync: jest.fn((k: string, v: string) => mockStore.set(k, v)),
    removeItemSync: jest.fn((k: string) => mockStore.delete(k)),
    clearSync: jest.fn(() => mockStore.clear()),
  },
}));

jest.mock('expo-router', () => ({
  useLocalSearchParams: () => ({}),
}));

jest.mock('@/services/alerts', () => ({
  speak: jest.fn(),
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Medium: 'medium' },
  NotificationFeedbackType: { Warning: 'warning', Success: 'success' },
}));

async function setupHarness(options: UseCalibrationMachineOptions) {
  let machine!: UseCalibrationMachineReturn;
  function Harness(props: UseCalibrationMachineOptions) {
    machine = useCalibrationMachine(props);
    return null;
  }
  const view = await render(<Harness {...options} />);
  return {
    get machine() {
      return machine;
    },
    rerender: (newOptions: UseCalibrationMachineOptions) =>
      view.rerender(<Harness {...newOptions} />),
    unmount: view.unmount,
  };
}

describe('useCalibrationMachine', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockStore.clear();
    useSettings.getState().reset();
    useLive.setState({ connection: 'offline' });
  });

  it('starts in intro step and moves to framing on start()', async () => {
    const harness = await setupHarness({ subscribe: () => () => {} });
    expect(harness.machine.step).toBe('intro');

    await act(async () => {
      harness.machine.start();
    });

    expect(harness.machine.step).toBe('framing');
    expect(harness.machine.framing).toEqual({
      faceInOval: false,
      lightOk: false,
      headStraight: false,
    });
  });

  it('cancel() returns to intro from framing', async () => {
    const harness = await setupHarness({ subscribe: () => () => {} });

    await act(async () => {
      harness.machine.start();
    });
    expect(harness.machine.step).toBe('framing');

    await act(async () => {
      harness.machine.cancel();
    });
    expect(harness.machine.step).toBe('intro');
  });

  it('auto-advances from framing to open after 1 s of stable conditions', async () => {
    let subscriber: ((sample: FaceSample) => void) | null = null;
    let fakeTime = 1000;

    const harness = await setupHarness({
      subscribe: (cb) => {
        subscriber = cb;
        return () => {
          subscriber = null;
        };
      },
      now: () => fakeTime,
    });

    await act(async () => {
      harness.machine.start();
    });
    expect(harness.machine.step).toBe('framing');

    // Partial face condition (not stable)
    await act(async () => {
      subscriber?.({
        faceFound: true,
        faceBoxFraction: 0.1, // too small
        luma: 50,
        yaw: 0,
        pitch: 0,
        ear: 0.3,
        earLeft: 0.3,
        earRight: 0.3,
        earValid: true,
        t: fakeTime,
      });
    });
    expect(harness.machine.framing.faceInOval).toBe(false);
    expect(harness.machine.isStable).toBe(false);
    expect(harness.machine.step).toBe('framing');

    // All conditions satisfied -> begins stable timer
    await act(async () => {
      subscriber?.({
        faceFound: true,
        faceBoxFraction: 0.5,
        luma: 60,
        yaw: 0,
        pitch: 0,
        ear: 0.3,
        earLeft: 0.3,
        earRight: 0.3,
        earValid: true,
        t: fakeTime,
      });
    });
    expect(harness.machine.framing.faceInOval).toBe(true);
    expect(harness.machine.framing.lightOk).toBe(true);
    expect(harness.machine.framing.headStraight).toBe(true);
    expect(harness.machine.isStable).toBe(true);
    expect(harness.machine.step).toBe('framing');

    // Advance time by 1000 ms with stable sample
    fakeTime += 1000;
    await act(async () => {
      subscriber?.({
        faceFound: true,
        faceBoxFraction: 0.5,
        luma: 60,
        yaw: 0,
        pitch: 0,
        ear: 0.3,
        earLeft: 0.3,
        earRight: 0.3,
        earValid: true,
        t: fakeTime,
      });
    });

    expect(harness.machine.step).toBe('open');
    expect(alerts.speak).toHaveBeenCalledWith('cal.eye.voice.open', undefined);
  });

  it('runs complete flow with fake source: framing -> open -> closed -> result', async () => {
    jest.useFakeTimers();
    let fakeTime = 10000;

    const fakeSource = createFakeFaceSource({
      script: 'openThenClosed',
      now: () => fakeTime,
    });

    const harness = await setupHarness({
      subscribe: fakeSource.subscribe,
      now: () => fakeTime,
    });

    await act(async () => {
      harness.machine.start();
    });
    expect(harness.machine.step).toBe('framing');

    // Deliver samples to stabilize framing (1000ms stable needed)
    for (let t = 0; t < 1200; t += 66) {
      fakeTime += 66;
      await act(async () => {
        jest.advanceTimersByTime(66);
      });
    }

    expect(harness.machine.step).toBe('open');
    expect(alerts.speak).toHaveBeenCalledWith('cal.eye.voice.open', undefined);

    // Run 10 seconds of open step
    for (let t = 0; t < 10000; t += 250) {
      fakeTime += 250;
      await act(async () => {
        jest.advanceTimersByTime(250);
      });
    }

    expect(harness.machine.step).toBe('closed');
    expect(alerts.speak).toHaveBeenCalledWith('cal.eye.voice.closed', undefined);

    // Run 3 seconds of closed step
    for (let t = 0; t < 3000; t += 250) {
      fakeTime += 250;
      await act(async () => {
        jest.advanceTimersByTime(250);
      });
    }

    expect(alerts.speak).toHaveBeenCalledWith('cal.eye.voice.done', undefined);
    expect(harness.machine.step).toBe('result');
    expect(harness.machine.resultPayload).not.toBeNull();
    expect(harness.machine.resultPayload?.quality).toBe('good');

    jest.useRealTimers();
  });

  it('handles eyesNotShut failure script: results in failed step with eyes_not_shut reason', async () => {
    jest.useFakeTimers();
    let fakeTime = 30000;

    const fakeSource = createFakeFaceSource({
      script: 'eyesNotShut',
      now: () => fakeTime,
    });

    const harness = await setupHarness({
      subscribe: fakeSource.subscribe,
      now: () => fakeTime,
    });

    await act(async () => {
      harness.machine.start();
    });

    // Advance framing
    for (let t = 0; t < 1200; t += 66) {
      fakeTime += 66;
      await act(async () => {
        jest.advanceTimersByTime(66);
      });
    }

    expect(harness.machine.step).toBe('open');

    // 10s open
    for (let t = 0; t < 10000; t += 250) {
      fakeTime += 250;
      await act(async () => {
        jest.advanceTimersByTime(250);
      });
    }

    expect(harness.machine.step).toBe('closed');

    // 3s closed
    for (let t = 0; t < 3000; t += 250) {
      fakeTime += 250;
      await act(async () => {
        jest.advanceTimersByTime(250);
      });
    }

    expect(harness.machine.step).toBe('failed');
    expect(harness.machine.failureReason).toBe('eyes_not_shut');

    // Retry should return to framing
    await act(async () => {
      harness.machine.retry();
    });
    expect(harness.machine.step).toBe('framing');
    expect(harness.machine.failureReason).toBeNull();

    jest.useRealTimers();
  });

  it('keeps parked framing step on framing after 5 s of fake timers, while un-parked flow advances after ~1 s stable', async () => {
    jest.useFakeTimers();
    let fakeTime = 1000;

    // 1. Parked framing flow: override is set
    const parkedSource = createFakeFaceSource({
      script: 'openThenClosed',
      now: () => fakeTime,
    });
    const parkedHarness = await setupHarness({
      subscribe: parkedSource.subscribe,
      calOverride: 'framing',
      now: () => fakeTime,
    });

    expect(parkedHarness.machine.step).toBe('framing');
    expect(parkedHarness.machine.framing).toEqual({
      faceInOval: true,
      lightOk: true,
      headStraight: true,
    });
    expect(parkedHarness.machine.isStable).toBe(true);

    // Advance 5 s with fake timers
    for (let t = 0; t < 5000; t += 250) {
      fakeTime += 250;
      await act(async () => {
        jest.advanceTimersByTime(250);
      });
    }

    // Must remain parked on framing step with ticks green
    expect(parkedHarness.machine.step).toBe('framing');
    expect(parkedHarness.machine.framing).toEqual({
      faceInOval: true,
      lightOk: true,
      headStraight: true,
    });
    expect(parkedHarness.machine.isStable).toBe(true);

    // 2. Un-parked flow: no override, starts at intro and advances after ~1 s stable
    fakeTime = 1000;
    const unparkedSource = createFakeFaceSource({
      script: 'openThenClosed',
      now: () => fakeTime,
    });
    const unparkedHarness = await setupHarness({
      subscribe: unparkedSource.subscribe,
      now: () => fakeTime,
    });

    await act(async () => {
      unparkedHarness.machine.start();
    });
    expect(unparkedHarness.machine.step).toBe('framing');

    // Deliver samples for ~1.2 s (over 1 s stable threshold)
    for (let t = 0; t < 1200; t += 66) {
      fakeTime += 66;
      await act(async () => {
        jest.advanceTimersByTime(66);
      });
    }

    expect(unparkedHarness.machine.step).toBe('open');

    jest.useRealTimers();
  });

  it('handles failure scripts correctly and retry resets state', async () => {
    jest.useFakeTimers();
    let fakeTime = 20000;

    const fakeSource = createFakeFaceSource({
      script: 'tooDark',
      now: () => fakeTime,
    });

    const harness = await setupHarness({
      subscribe: fakeSource.subscribe,
      now: () => fakeTime,
    });

    await act(async () => {
      harness.machine.start();
    });

    // In tooDark, luma=20 so lightOk is false
    expect(harness.machine.framing.lightOk).toBe(false);

    // Test retry
    await act(async () => {
      harness.machine.retry();
    });
    expect(harness.machine.step).toBe('framing');

    jest.useRealTimers();
  });

  it('saves eyeCalibration to store and handles offline vs online sync', async () => {
    jest.spyOn(sync, 'syncEyeCalibration').mockImplementation(async () => {
      const isOnline = useLive.getState().connection === 'online';
      if (isOnline) {
        useSettings.getState().setEyeCalibration({
          ...useSettings.getState().eyeCalibration!,
          syncedAt: Date.now(),
        });
        return 'ok';
      }
      return 'skipped';
    });

    // Park in good result via override
    const harness = await setupHarness({
      subscribe: () => () => {},
      calOverride: 'good',
    });

    expect(harness.machine.step).toBe('result');
    expect(harness.machine.isSaved).toBe(false);
    expect(harness.machine.isSynced).toBe(false);

    // 1. Save while unit is OFFLINE
    useLive.setState({ connection: 'offline' });
    await act(async () => {
      harness.machine.save();
    });

    expect(harness.machine.isSaved).toBe(true);
    expect(harness.machine.isSynced).toBe(false);
    expect(useSettings.getState().eyeCalibration).not.toBeNull();
    expect(useSettings.getState().eyeCalibration?.syncedAt).toBeNull();

    // 2. Save while unit is ONLINE
    useLive.setState({ connection: 'online' });
    await act(async () => {
      harness.machine.save();
    });

    expect(harness.machine.isSaved).toBe(true);
    expect(harness.machine.isSynced).toBe(true);
    expect(useSettings.getState().eyeCalibration?.syncedAt).not.toBeNull();
  });

  it('respects calOverride query params for screenshots', async () => {
    const framingHarness = await setupHarness({
      subscribe: () => () => {},
      calOverride: 'framing',
    });
    expect(framingHarness.machine.step).toBe('framing');
    expect(framingHarness.machine.secondsRemaining).toBe(10);
    expect(framingHarness.machine.isStable).toBe(true);
    expect(framingHarness.machine.framing).toEqual({
      faceInOval: true,
      lightOk: true,
      headStraight: true,
    });

    const openHarness = await setupHarness({
      subscribe: () => () => {},
      calOverride: 'open',
    });
    expect(openHarness.machine.step).toBe('open');
    expect(openHarness.machine.secondsRemaining).toBe(5);

    const closedHarness = await setupHarness({
      subscribe: () => () => {},
      calOverride: 'closed',
    });
    expect(closedHarness.machine.step).toBe('closed');
    expect(closedHarness.machine.secondsRemaining).toBe(2);

    const poorHarness = await setupHarness({
      subscribe: () => () => {},
      calOverride: 'poor',
    });
    expect(poorHarness.machine.step).toBe('result');
    expect(poorHarness.machine.resultPayload?.quality).toBe('poor');

    const failHarness = await setupHarness({
      subscribe: () => () => {},
      calOverride: 'failure',
    });
    expect(failHarness.machine.step).toBe('failed');
    expect(failHarness.machine.failureReason).toBe('no_face');
  });
});
