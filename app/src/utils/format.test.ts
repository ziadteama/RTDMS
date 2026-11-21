import { formatDuration } from './format';

const u = { h: 'h', min: 'min', s: 's' };

it('formats durations for trip rows', () => {
  expect(formatDuration(45_000, u)).toBe('45 s');
  expect(formatDuration(12 * 60_000, u)).toBe('12 min');
  expect(formatDuration(65 * 60_000, u)).toBe('1 h 05 min');
});
