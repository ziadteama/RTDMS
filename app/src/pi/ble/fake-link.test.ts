import { FakeBleLink } from './fake-link';

describe('FakeBleLink', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  it('autoplay emits alert, status, and physio while online', () => {
    const link = new FakeBleLink();
    link.start({ name: 'RTDMS-Pi', token: 'k3Jx9mQ2pL7vN4wR8tY1' });
    link.setState('online');

    const emitted: string[] = [];
    link.onNotify((n) => emitted.push(n.kind));

    const stopAutoplay = link.autoplay(() => 10);
    expect(emitted).toEqual(['alert', 'status', 'physio']);

    jest.advanceTimersByTime(1000);
    expect(emitted.length).toBe(6);

    stopAutoplay();
    jest.advanceTimersByTime(1000);
    expect(emitted.length).toBe(6);
  });

  it('stops autoplay when setState is offline or stop() is called', () => {
    const link = new FakeBleLink();
    link.start({ name: 'RTDMS-Pi', token: 'k3Jx9mQ2pL7vN4wR8tY1' });
    link.setState('online');

    const emitted: string[] = [];
    link.onNotify((n) => emitted.push(n.kind));

    link.autoplay(() => 10);
    expect(emitted.length).toBe(3);

    link.setState('offline');
    jest.advanceTimersByTime(1000);
    expect(emitted.length).toBe(3);
  });
});
