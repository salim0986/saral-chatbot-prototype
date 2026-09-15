import { render, screen, fireEvent } from '@testing-library/react';
import { MessageBubble } from '../components/MessageBubble';
import { describe, it, expect, vi } from 'vitest';

describe('MessageBubble Component', () => {
  it('renders user message correctly', () => {
    render(<MessageBubble role="user" content="Hello World" />);
    expect(screen.getByText('Hello World')).toBeInTheDocument();
    
    // The container should have bg-teal-600
    const container = screen.getByText('Hello World').parentElement;
    expect(container).toHaveClass('bg-teal-600');
  });

  it('renders assistant message with sentences and badges', () => {
    const sentences = [
      { text: 'First sentence.', source_ids: ['c1'], source_pages: [1] },
      { text: 'Second sentence.', source_ids: ['c2', 'c3'], source_pages: [1] }
    ];

    const onBadgeClick = vi.fn();
    render(<MessageBubble role="assistant" sentences={sentences} onBadgeClick={onBadgeClick} />);
    
    expect(screen.getByText(/First sentence\./)).toBeInTheDocument();
    expect(screen.getByText(/Second sentence\./)).toBeInTheDocument();
    
    // There should be 3 badges (1 for first sentence, 2 for second)
    const badges = screen.getAllByRole('button');
    expect(badges).toHaveLength(3);
    
    // Test badge click
    fireEvent.click(badges[1]);
    expect(onBadgeClick).toHaveBeenCalledWith('c2');
  });

  it('does not render badges if source_ids is empty', () => {
    const sentences = [
      { text: 'No citations here.', source_ids: [], source_pages: [] }
    ];
    render(<MessageBubble role="assistant" sentences={sentences} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
