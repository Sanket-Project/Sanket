import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { Modal } from './Modal';

it('offers a wide bounded dialog with an independently scrollable body', () => {
  render(<Modal open onClose={() => {}} title="Import" size="wide">Report</Modal>);
  expect(screen.getByRole('dialog')).toHaveClass('max-w-[1600px]', 'max-h-[92dvh]');
  expect(screen.getByText('Report')).toHaveClass('overflow-y-auto');
});
