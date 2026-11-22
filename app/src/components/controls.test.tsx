import { fireEvent, render, screen } from '@testing-library/react-native';
import { View } from 'react-native';
import { Slider } from '@expo/ui';

import { Choice, SliderControl } from './controls';
import { Row } from './list';

jest.mock('@expo/ui', () => {
  const { View } = jest.requireActual('react-native');
  return { Host: View, Slider: jest.fn(() => null), Switch: View };
});
jest.mock('expo-symbols', () => ({ SymbolView: () => null }));
jest.mock('react-native-safe-area-context', () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

const options = [{ value: 'off', label: 'Off' }, { value: 'strong', label: 'Strong' }];

it('shows the selected label, opens accessible options, selects and closes', async () => {
  const onChange = jest.fn();
  await render(<Choice value="off" options={options} onChange={onChange} label="Vibration" />);
  expect(screen.getByText('Off')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Vibration' }).props.accessibilityValue).toEqual({ text: 'Off' });
  await fireEvent.press(screen.getByRole('button', { name: 'Vibration' }));
  expect(screen.getByRole('header', { name: 'Vibration' })).toBeTruthy();
  expect(screen.getByRole('radio', { name: 'Off', checked: true })).toBeTruthy();
  await fireEvent.press(screen.getByRole('radio', { name: 'Strong', checked: false }));
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith('strong');
  expect(screen.queryByRole('radio')).toBeNull();
  expect(screen.getByRole('button', { name: 'Vibration' }).props.accessibilityState.expanded).toBe(false);
});

it('closes via backdrop or Android back without changing the value', async () => {
  const onChange = jest.fn();
  await render(<Choice value="off" options={options} onChange={onChange} label="Vibration" />);
  await fireEvent.press(screen.getByRole('button', { name: 'Vibration' }));
  await fireEvent.press(screen.getByRole('button', { name: 'Close options' }));
  expect(screen.queryByRole('radio')).toBeNull();
  await fireEvent.press(screen.getByRole('button', { name: 'Vibration' }));
  await fireEvent(screen.getByTestId('choice-sheet'), 'requestClose');
  expect(screen.queryByRole('radio')).toBeNull();
  expect(onChange).not.toHaveBeenCalled();
});

it('does not open when disabled and truncates long labels', async () => {
  await render(<Choice value="ambulance" options={[{ value: 'ambulance', label: 'Ambulance (123)' }]}
    onChange={jest.fn()} label="Call target" disabled />);
  expect(screen.getByText('Ambulance (123)').props.numberOfLines).toBe(1);
  const trigger = screen.getByRole('button', { name: 'Call target', disabled: true });
  await fireEvent.press(trigger);
  expect(screen.queryByRole('radio')).toBeNull();
});

it.each([
  [0.1, 0.26, 0.3], [0.1, 0.30000000000000004, 0.3], [0.25, 0.63, 0.75], [1e-7, 0.00000026, 0.0000003],
])('snaps step %s without float noise', async (step, input, expected) => {
  const onChange = jest.fn();
  await render(<SliderControl value={0} min={0} max={1} step={step} onChange={onChange} />);
  const props = jest.mocked(Slider).mock.calls.at(-1)![0];
  expect(props).not.toHaveProperty('step');
  props.onValueChange!(input);
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith(expected);
});

it('clamps slider values and suppresses unchanged snapped values', async () => {
  const onChange = jest.fn();
  await render(<SliderControl value={0.3} min={0.1} max={0.95} step={0.1} onChange={onChange} />);
  const props = jest.mocked(Slider).mock.calls.at(-1)![0];
  props.onValueChange!(0.31);
  expect(onChange).not.toHaveBeenCalled();
  props.onValueChange!(-1);
  props.onValueChange!(2);
  expect(onChange.mock.calls).toEqual([[0.1], [0.95]]);
  await render(<SliderControl value={2} min={0} max={1} onChange={onChange} />);
  expect(jest.mocked(Slider).mock.calls.at(-1)![0].value).toBe(1);
});

it('reserves label width and bounds the right slot while preserving value text', async () => {
  await render(<Row label="Vibration" value="Current" right={<View testID="control" />} />);
  expect(screen.getByText('Vibration').parent?.props.style).toMatchObject({ flex: 1, minWidth: '40%' });
  expect(screen.getByTestId('control').parent?.props.style).toEqual({ flexShrink: 0, maxWidth: '55%' });
  expect(screen.getByText('Current')).toBeTruthy();
});
