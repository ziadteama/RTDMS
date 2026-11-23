import { adaptAlert } from './ble/adapt';
import { parseAlert } from './parse';

test.each([undefined, null, '1', 0, -1, 1.5, Infinity, NaN, {}, 1, 42])('parses and adapts episode %p', (episode) => {
  const value = { pattern: 'max', reasons: [], t: 1, emergency: 'unresponsive', episode };
  const expected = episode === 1 || episode === 42 ? episode : null;
  expect(adaptAlert(value)?.episode).toBe(expected);
  expect(parseAlert(value)?.episode).toBe(expected);
  expect(parseAlert(adaptAlert(value))).toEqual(parseAlert(value));
  expect(parseAlert(value)?.emergency).toBe('unresponsive');
});
