import React from 'react';
import { render } from '@testing-library/react-native';

import { SahiFaceView, isFaceViewAvailable } from '../SahiFaceView';

describe('SahiFaceView in non-native / Jest environment', () => {
  it('reports isFaceViewAvailable as false in Jest', () => {
    expect(isFaceViewAvailable()).toBe(false);
  });

  it('renders null safely without throwing', async () => {
    const onFace = jest.fn();
    const { toJSON } = await render(<SahiFaceView onFace={onFace} active />);
    expect(toJSON()).toBeNull();
  });
});
