import { render, screen, fireEvent } from '@testing-library/react';
import { DeltaView, DiffHunk } from '../components/DeltaView';
import { describe, it, expect, vi } from 'vitest';

describe('DeltaView Component', () => {
  const mockOnAccept = vi.fn();
  const mockOnReject = vi.fn();

  const hunks: DiffHunk[] = [
    { operation: 'equal', text: 'This is ' },
    { operation: 'delete', text: 'hard' },
    { operation: 'insert', text: 'easy' },
    { operation: 'equal', text: ' to read.' }
  ];

  it('renders diff hunks correctly', () => {
    render(<DeltaView diffHunks={hunks} reason="Simplified it." onAccept={mockOnAccept} />);
    
    expect(screen.getByText('This is')).toBeInTheDocument();
    expect(screen.getByText('hard')).toBeInTheDocument();
    expect(screen.getByText('easy')).toBeInTheDocument();
    expect(screen.getByText('to read.')).toBeInTheDocument();
    
    expect(screen.getByText('Reason: Simplified it.')).toBeInTheDocument();
    
    expect(screen.getByTestId('diff-delete')).toHaveTextContent('hard');
    expect(screen.getByTestId('diff-insert')).toHaveTextContent('easy');
  });

  it('calls onAccept when accept button is clicked', () => {
    render(<DeltaView diffHunks={hunks} reason="reason" onAccept={mockOnAccept} />);
    
    const acceptBtn = screen.getByTestId('accept-btn');
    fireEvent.click(acceptBtn);
    expect(mockOnAccept).toHaveBeenCalled();
  });

  it('renders reject button if provided', () => {
    render(<DeltaView diffHunks={hunks} reason="reason" onAccept={mockOnAccept} onReject={mockOnReject} />);
    
    const rejectBtn = screen.getByTestId('reject-btn');
    expect(rejectBtn).toBeInTheDocument();
    
    fireEvent.click(rejectBtn);
    expect(mockOnReject).toHaveBeenCalled();
  });
});
