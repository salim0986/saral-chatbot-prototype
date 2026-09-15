import { render, screen, fireEvent } from '@testing-library/react';
import { ChatWindow } from '../components/ChatWindow';
import { describe, it, expect, vi } from 'vitest';

describe('ChatWindow Component', () => {
  const mockOnSendMessage = vi.fn();
  const mockOnBadgeClick = vi.fn();
  
  // Mock scrollIntoView
  window.HTMLElement.prototype.scrollIntoView = vi.fn();

  it('renders empty state initially', () => {
    render(
      <ChatWindow 
        messages={[]} 
        isLoading={false} 
        onSendMessage={mockOnSendMessage} 
        onBadgeClick={mockOnBadgeClick} 
      />
    );
    expect(screen.getByText(/Ready to generate content/)).toBeInTheDocument();
  });

  it('renders messages and handles input', () => {
    const messages = [
      { role: 'user' as const, content: 'Hello' },
      { role: 'assistant' as const, content: 'Hi there' }
    ];

    render(
      <ChatWindow 
        messages={messages} 
        isLoading={false} 
        onSendMessage={mockOnSendMessage} 
        onBadgeClick={mockOnBadgeClick} 
      />
    );
    
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('Hi there')).toBeInTheDocument();

    const input = screen.getByTestId('chat-input');
    fireEvent.change(input, { target: { value: 'New message' } });
    
    const button = screen.getByText('Send');
    fireEvent.click(button);
    
    expect(mockOnSendMessage).toHaveBeenCalledWith('New message');
  });

  it('shows loading indicator and disables input', () => {
    render(
      <ChatWindow 
        messages={[]} 
        isLoading={true} 
        onSendMessage={mockOnSendMessage} 
        onBadgeClick={mockOnBadgeClick} 
      />
    );
    
    expect(screen.getByTestId('loading-indicator')).toBeInTheDocument();
    expect(screen.getByTestId('chat-input')).toBeDisabled();
    expect(screen.getByText('Send')).toBeDisabled();
  });
});
