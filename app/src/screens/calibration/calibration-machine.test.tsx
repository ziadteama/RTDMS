import { act, fireEvent, render } from '@testing-library/react-native';
import React from 'react';
import { Linking } from 'react-native';

import { createFakeFaceSource, type FaceSample, type CalibrationTransport } from './adapters';
import { EyeCalibrationScreen } from './index';
import { IntroStep } from './intro-step';
import { ResultStep } from './result-step';
import {
  useCalibrationMachine,
  type UseCalibrationMachineOptions,
  type UseCalibrationMachineReturn,
} from './use-calibration-machine';
import * as permissions from '@/services/permissions';
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

jest.mock('expo-symbols', () => ({ SymbolView: () => null }));

jest.mock('expo-keep-awake', () => ({
  useKeepAwake: jest.fn(),
  activateKeepAwakeAsync: jest.fn(),
  deactivateKeepAwake: jest.fn(),
}));

let mockNativeAvailable = false;
let mockMountCount = 0;
let mockUnmountCount = 0;
let mockFaceListener: ((sample: FaceSample) => void) | null = null;

jest.mock('@modules/sahi-native', () => {
  const actual = jest.requireActual<typeof import('@modules/sahi-native')>('@modules/sahi-native');
  const ReactActual = jest.requireActual<typeof import('react')>('react');
  const { View: RNView } = jest.requireActual<typeof import('react-native')>('react-native');

  return {
    ...actual,
    isFaceViewAvailable: () => mockNativeAvailable,
    SahiFaceView: (props: { active?: boolean; onFace: (sample: FaceSample) => void }) => {
      ReactActual.useEffect(() => {
        mockMountCount++;
        mockFaceListener = props.onFace;
        return () => {
          mockUnmountCount++;
          mockFaceListener = null;
        };
      }, [props.onFace]);
      return <RNView testID="mock-sahi-face-view" />;
    },
  };
});

jest.mock('react-native-reanimated', () => {
  const { View: RNView } = jest.requireActual<typeof import('react-native')>('react-native');
  return {
    __esModule: true,
    default: {
      View: RNView,
    },
    useReducedMotion: () => true,
    cubicBezier: () => () => 0,
    useSharedValue: (init: unknown) => ({
      value: init,
      set: jest.fn(),
      get: () => init,
    }),
    useAnimatedStyle: () => ({}),
    withTiming: (toValue: unknown) => toValue,
    cancelAnimation: jest.fn(),
    Easing: {
      linear: (v: unknown) => v,
    },
  };
});

async function setupHarness(options: UseCalibrationMachineOptions) {
  let machine!: UseCalibrationMachineReturn;
  function Harness(props: UseCalibrationMachineOptions) {
    machine = useCalibrationMachine({
      ...props,
      now: props.now ? () => props.now!() : undefined,
    });
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
    const syncSpy = jest.spyOn(sync, 'syncEyeCalibration').mockImplementation(async () => {
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
    syncSpy.mockRestore();
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

  it('handles NON-stable inline now option: open phase completes and cue fires once despite ~15 Hz sample stream', async () => {
    let fakeTime = 10000;
    let subscriber: ((sample: FaceSample) => void) | null = null;

    const harness = await setupHarness({
      subscribe: (cb) => {
        subscriber = cb;
        return () => {
          subscriber = null;
        };
      },
      now: () => fakeTime,
    });

    jest.useFakeTimers();

    await act(async () => {
      harness.machine.start();
    });
    expect(harness.machine.step).toBe('framing');

    const goodSample: FaceSample = {
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
    };

    await act(async () => {
      for (let t = 0; t < 1200; t += 66) {
        fakeTime += 66;
        subscriber?.({ ...goodSample, t: fakeTime });
        jest.advanceTimersByTime(66);
      }
    });

    expect(harness.machine.step).toBe('open');
    expect(alerts.speak).toHaveBeenCalledWith('cal.eye.voice.open', undefined);
    expect(alerts.speak).toHaveBeenCalledTimes(1);

    await act(async () => {
      for (let t = 0; t < 10000; t += 66) {
        fakeTime += 66;
        subscriber?.({ ...goodSample, t: fakeTime });
        jest.advanceTimersByTime(66);
      }
      jest.advanceTimersByTime(250);
    });

    expect(harness.machine.step).toBe('closed');
    expect((alerts.speak as jest.Mock).mock.calls.filter((c) => c[0] === 'cal.eye.voice.open')).toHaveLength(1);
    expect(alerts.speak).toHaveBeenCalledWith('cal.eye.voice.closed', undefined);

    jest.useRealTimers();
  });

  it('saves with syncedAt null initially, handles injected transport, and demo mode never claims sent', async () => {
    let sentPayload: unknown = null;
    const fakeTransport: CalibrationTransport = {
      send: jest.fn(async (payload) => {
        sentPayload = payload;
        useSettings.getState().setEyeCalibration({
          ...useSettings.getState().eyeCalibration!,
          syncedAt: Date.now(),
        });
        return 'ok';
      }),
    };

    const harness = await setupHarness({
      subscribe: () => () => {},
      calOverride: 'good',
      transport: fakeTransport,
    });

    expect(harness.machine.step).toBe('result');
    expect(harness.machine.isSaved).toBe(false);
    expect(harness.machine.isSynced).toBe(false);

    // 1. In demo mode: never claims sent and transport is never sent
    useSettings.getState().set({ demo: true });
    await act(async () => {
      harness.machine.save();
    });

    expect(harness.machine.isSaved).toBe(true);
    expect(harness.machine.isSynced).toBe(false);
    expect(useSettings.getState().eyeCalibration?.syncedAt).toBeNull();
    expect(fakeTransport.send).not.toHaveBeenCalled();

    // 2. Online with injected transport
    useSettings.getState().set({ demo: false });
    useLive.setState({ connection: 'online' });
    await act(async () => {
      harness.machine.save();
    });

    expect(harness.machine.isSaved).toBe(true);
    expect(harness.machine.isSynced).toBe(true);
    expect(useSettings.getState().eyeCalibration?.syncedAt).not.toBeNull();
    expect(fakeTransport.send).toHaveBeenCalledTimes(1);
    expect(sentPayload).not.toBeNull();
  });

  it('ResultStep for poor quality shows only Retry, advice line and Cancel button, no Save', async () => {
    const onSave = jest.fn();
    const onRetry = jest.fn();
    const onDone = jest.fn();

    const view = await render(
      <ResultStep
        quality="poor"
        isSaved={false}
        isSynced={false}
        onSave={onSave}
        onRetry={onRetry}
        onDone={onDone}
      />
    );

    expect(view.getByText('Retry')).toBeTruthy();
    expect(view.getByText('Cancel')).toBeTruthy();
    expect(
      view.getByText(
        'Low contrast between open and closed eyes. Ensure good lighting and keep eyes fully closed during the second step.'
      )
    ).toBeTruthy();

    expect(view.queryByText('Save')).toBeNull();
    expect(view.queryByText('Save anyway')).toBeNull();

    fireEvent.press(view.getByText('Cancel'));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it('IntroStep requests camera permission: starts if granted, shows message and settings if denied', async () => {
    const onStart = jest.fn();
    const openSettingsSpy = jest.spyOn(Linking, 'openSettings').mockImplementation(async () => {});
    const permSpy = jest.spyOn(permissions, 'permission').mockResolvedValue('denied');

    const view = await render(<IntroStep onStart={onStart} />);
    const startBtn = view.getByText('Start');

    await act(async () => {
      fireEvent.press(startBtn);
      await Promise.resolve();
    });

    expect(onStart).not.toHaveBeenCalled();
    expect(view.getByText('Camera access is needed to measure your eyes.')).toBeTruthy();
    const settingsBtn = view.getByText('Open settings');
    expect(settingsBtn).toBeTruthy();

    await act(async () => {
      fireEvent.press(settingsBtn);
    });
    expect(openSettingsSpy).toHaveBeenCalledTimes(1);

    permSpy.mockResolvedValue('granted');
    await act(async () => {
      fireEvent.press(view.getByText('Start'));
      await Promise.resolve();
    });

    expect(onStart).toHaveBeenCalledTimes(1);
    openSettingsSpy.mockRestore();
    permSpy.mockRestore();
  });

  it('save() refuses when result quality is poor or there is no payload', async () => {
    // 1. No payload
    const harnessNoPayload = await setupHarness({
      subscribe: () => () => {},
    });
    expect(harnessNoPayload.machine.resultPayload).toBeNull();
    await act(async () => {
      harnessNoPayload.machine.save();
    });
    expect(harnessNoPayload.machine.isSaved).toBe(false);
    expect(useSettings.getState().eyeCalibration).toBeNull();

    // 2. Poor quality payload via override
    const harnessPoor = await setupHarness({
      subscribe: () => () => {},
      calOverride: 'poor',
    });
    expect(harnessPoor.machine.resultPayload?.quality).toBe('poor');
    await act(async () => {
      harnessPoor.machine.save();
    });
    expect(harnessPoor.machine.isSaved).toBe(false);
    expect(useSettings.getState().eyeCalibration).toBeNull();
  });

  it('IntroStep fails open when camera permission module is unavailable or throws', async () => {
    const onStart = jest.fn();
    const permSpy = jest.spyOn(permissions, 'permission').mockRejectedValue(new Error('Native module not found'));

    const view = await render(<IntroStep onStart={onStart} />);
    const startBtn = view.getByText('Start');

    await act(async () => {
      fireEvent.press(startBtn);
      await Promise.resolve();
    });

    expect(onStart).toHaveBeenCalledTimes(1);
    permSpy.mockRestore();
  });

  it('calibration screen keeps SahiFaceView mounted once across framing -> open -> closed, unmounts on result, and samples reach collectors', async () => {
    jest.useFakeTimers();
    mockNativeAvailable = true;
    mockMountCount = 0;
    mockUnmountCount = 0;
    mockFaceListener = null;

    let fakeTime = 10000;
    const fakeSource = createFakeFaceSource({
      script: 'openThenClosed',
      now: () => fakeTime,
    });

    fakeSource.subscribe((sample) => {
      mockFaceListener?.(sample);
    });

    const permSpy = jest.spyOn(permissions, 'permission').mockResolvedValue('granted');

    const screen = await render(<EyeCalibrationScreen onDone={jest.fn()} />);

    // 1. Intro step: face view not mounted yet
    expect(mockMountCount).toBe(0);
    expect(mockUnmountCount).toBe(0);

    // 2. Press start -> transition to framing
    const startButton = screen.getByText('Start');
    await act(async () => {
      fireEvent.press(startButton);
    });

    // Face view should now be mounted ONCE
    expect(mockMountCount).toBe(1);
    expect(mockUnmountCount).toBe(0);

    // 3. Advance fake timers to satisfy framing stability (1200ms of ~66ms intervals)
    for (let t = 0; t < 1200; t += 66) {
      fakeTime += 66;
      await act(async () => {
        jest.advanceTimersByTime(66);
      });
    }

    // Step should now be 'open' - face view must STILL be mounted once with 0 unmounts
    expect(mockMountCount).toBe(1);
    expect(mockUnmountCount).toBe(0);

    // 4. Advance through 10s of open phase
    for (let t = 0; t < 10000; t += 66) {
      fakeTime += 66;
      await act(async () => {
        jest.advanceTimersByTime(66);
      });
    }
    await act(async () => {
      jest.advanceTimersByTime(250);
    });

    // Step should now be 'closed' - face view must STILL be mounted once with 0 unmounts
    expect(mockMountCount).toBe(1);
    expect(mockUnmountCount).toBe(0);

    // 5. Advance through 3s of closed phase
    for (let t = 0; t < 3000; t += 66) {
      fakeTime += 66;
      await act(async () => {
        jest.advanceTimersByTime(66);
      });
    }
    await act(async () => {
      jest.advanceTimersByTime(250);
    });

    // 6. Step should now be 'result'
    // Face view must now be UNMOUNTED on result step
    expect(mockMountCount).toBe(1);
    expect(mockUnmountCount).toBe(1);

    // Verify samples reached open and closed collectors:
    // Successful profile build shows Save button and good result title
    expect(screen.getByText('Save')).toBeTruthy();
    expect(screen.getByText('Good calibration')).toBeTruthy();

    permSpy.mockRestore();
    mockNativeAvailable = false;
    jest.useRealTimers();
  });
});
